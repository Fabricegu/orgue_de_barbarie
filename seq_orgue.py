import mido
import time
from threading import Thread, Event, Lock


def list_and_choose_ports():
    # Lister les ports d'entrée et de sortie
    input_ports = mido.get_input_names()
    output_ports = mido.get_output_names()

    if not input_ports and not output_ports:
        print("Aucun port MIDI disponible.")
        return None, None

    print("=== Ports MIDI d'entrée disponibles ===")
    if input_ports:
        for i, port in enumerate(input_ports):
            print(f"{i + 1}: {port}")
    else:
        print("Aucun port d'entrée MIDI disponible.")

    print("\n=== Ports MIDI de sortie disponibles ===")
    if output_ports:
        for i, port in enumerate(output_ports):
            print(f"{i + 1}: {port}")
    else:
        print("Aucun port de sortie MIDI disponible.")

    # Permettre à l'utilisateur de choisir un port de sortie
    chosen_output_port = None
    if output_ports:
        while True:
            try:
                output_choice = int(input("\nChoisissez un port MIDI de sortie (par numéro) : "))
                if 1 <= output_choice <= len(output_ports):
                    chosen_output_port = output_ports[output_choice - 1]
                    break
                else:
                    print("Numéro invalide. Réessayez.")
            except ValueError:
                print("Entrée non valide. Veuillez entrer un numéro.")

    # Permettre à l'utilisateur de choisir un port d'entrée
    chosen_input_port = None
    if input_ports:
        while True:
            try:
                input_choice = int(input("\nChoisissez un port MIDI d'entrée (par numéro) : "))
                if 1 <= input_choice <= len(input_ports):
                    chosen_input_port = input_ports[input_choice - 1]
                    break
                else:
                    print("Numéro invalide. Réessayez.")
            except ValueError:
                print("Entrée non valide. Veuillez entrer un numéro.")

    print(f"\nPort MIDI de sortie sélectionné : {chosen_output_port}")
    print(f"Port MIDI d'entrée sélectionné : {chosen_input_port}")

    return chosen_input_port, chosen_output_port

'''
# Lister les ports MIDI disponibles
def list_ports():
    output_ports = mido.get_output_names()
    if not output_ports:
        print("Aucun port MIDI disponible.")
        return None
    print("Ports MIDI disponibles :")
    for i, port in enumerate(output_ports):
        print(f"{i + 1}: {port}")
    return output_ports

# Permettre à l'utilisateur de choisir un port MIDI
def choose_port(ports):
    while True:
        try:
            choice = int(input("Choisissez un port MIDI (par numéro) : "))
            if 1 <= choice <= len(ports):
                return ports[choice - 1]
            else:
                print("Numéro invalide. Réessayez.")
        except ValueError:
            print("Entrée non valide. Veuillez entrer un numéro.")
'''
# Conversion des ticks MIDI en secondes
def ticks_to_seconds(ticks, tempo, ticks_per_beat):
    return ticks * (tempo / 1_000_000) / ticks_per_beat

# Envoyer une commande "Panic" pour arrêter toutes les notes
def send_panic(outport):
    for channel in range(16):  # 16 canaux MIDI
        outport.send(mido.Message('control_change', channel=channel, control=120, value=0))  # All Sound Off
        outport.send(mido.Message('control_change', channel=channel, control=123, value=0))  # All Notes Off
    print("Commande PANIC envoyée : toutes les notes arrêtées.")

# Gestion des commandes utilisateur (STOP, PAUSE, RESUME, etc.)
def handle_user_input(active_tracks, track_channels, transpose, outport, stop_event, pause_event, lock):
    while not stop_event.is_set():
        command = input("Entrez une commande (T <numéro>, TRANS <valeur>, PANIC, PAUSE, RESUME, STOP, Q) : ").strip().upper()
        if command.startswith("T "):  # Activer/désactiver une piste
            try:
                track_num = int(command.split()[1]) - 1
                if 0 <= track_num < len(active_tracks):
                    with lock:
                        if active_tracks[track_num]:  # Désactivation de la piste
                            channel = track_channels[track_num]
                            outport.send(mido.Message('control_change', channel=channel, control=123, value=0))
                            print(f"Piste {track_num + 1} désactivée (All Notes Off envoyée pour le canal {channel}).")
                        else:
                            print(f"Piste {track_num + 1} activée.")
                        active_tracks[track_num] = not active_tracks[track_num]
                else:
                    print("Numéro de piste invalide.")
            except ValueError:
                print("Commande invalide. Utilisez 'T <numéro>'.")
        elif command.startswith("TRANS "):  # Transposition en temps réel
            try:
                value = int(command.split()[1])
                with lock:
                    send_panic(outport)  # Arrêter toutes les notes avant la transposition
                    transpose[0] = value
                print(f"Transposition réglée à {value} demi-tons.")
            except ValueError:
                print("Commande invalide. Utilisez 'TRANS <valeur>'.")
        elif command == "PANIC":  # Arrêter toutes les notes immédiatement
            with lock:
                send_panic(outport)
        elif command == "PAUSE":  # Mettre la lecture en pause
            print("Séquenceur mis en pause.")
            pause_event.clear()
        elif command == "RESUME":  # Reprendre la lecture
            print("Séquenceur repris.")
            pause_event.set()
        elif command == "STOP":  # Arrêter complètement le séquencement
            print("Arrêt du séquenceur.")
            stop_event.set()
            break
        elif command == "Q":  # Quitter (équivalent à STOP)
            stop_event.set()
            break
        else:
            print("Commande non reconnue.")

# Lecture des pistes avec contrôle interactif
def play_midi_file_with_control(midi_file_path, output_port):
    midi_file = mido.MidiFile(midi_file_path)
    tempo = 500000  # Valeur par défaut (120 BPM)
    ticks_per_beat = midi_file.ticks_per_beat

    print(f"Lecture du fichier MIDI : {midi_file_path}")
    print(f"Nombre de pistes : {len(midi_file.tracks)}")

    # Initialisation des états des pistes (toutes activées par défaut)
    active_tracks = [True] * len(midi_file.tracks)

    # Déterminer les canaux MIDI pour chaque piste
    track_channels = []
    for track in midi_file.tracks:
        channel = None
        for msg in track:
            if msg.type == 'program_change' or (msg.type.startswith('note') and hasattr(msg, 'channel')):
                channel = msg.channel
                break
        track_channels.append(channel if channel is not None else 0)  # Par défaut, canal 0

    # Initialisation de la transposition (0 demi-tons par défaut)
    transpose = [0]  # Liste pour permettre un accès modifiable entre threads

    # Verrou pour synchroniser l'accès aux ressources partagées
    lock = Lock()

    # Événements pour gérer PAUSE et STOP
    stop_event = Event()
    pause_event = Event()
    pause_event.set()  # Par défaut, le séquencement est actif

    # Gestion des commandes utilisateur dans un thread séparé
    user_input_thread = Thread(target=handle_user_input, args=(active_tracks, track_channels, transpose, mido.open_output(output_port), stop_event, pause_event, lock))
    user_input_thread.start()

    # Fusionner les événements de toutes les pistes
    with mido.open_output(output_port) as outport:
        print(f"Envoi des notes au port MIDI : {output_port}")

        tracks_events = []
        for i, track in enumerate(midi_file.tracks):
            time_absolute = 0
            track_events = []
            for msg in track:
                time_absolute += msg.time
                if msg.is_meta and msg.type == 'set_tempo':
                    tempo = msg.tempo  # Mise à jour du tempo global
                else:
                    track_events.append((time_absolute, msg, i))  # Ajouter l'index de la piste
            tracks_events.extend(track_events)

        # Afficher les 3 premiers événements de tracks_events
        print("Les 3 premiers événements de tracks_events :")
        for event_time, msg, track_index in tracks_events[:3]:
        #for event_time, msg, track_index in tracks_events:
            print(f"Temps absolu: {event_time}, Piste: {track_index}, Message: {msg}")

        # Trier tous les événements par temps absolu
        tracks_events.sort(key=lambda x: x[0])

        # Afficher les 3 premiers événements de tracks_events
        print("Les 3 premiers événements de tracks_events :")
        for event_time, msg, track_index in tracks_events[:3]:
        #for event_time, msg, track_index in tracks_events:
            print(f"Temps absolu: {event_time}, Piste: {track_index}, Message: {msg}")

        # Lecture des événements
        start_time = time.time()
        for event_time, msg, track_index in tracks_events:
            if stop_event.is_set():
                break

            current_time = time.time()
            wait_time = ticks_to_seconds(event_time, tempo, ticks_per_beat) - (current_time - start_time)
            nbTicks = ticks_to_seconds(event_time, tempo, ticks_per_beat)
            print("nbTicks : ", nbTicks)
            if wait_time > 0:
                #print(f"Attendre {wait_time:.3f} secondes...")
                time.sleep(wait_time)

            # Attendre si en pause
            while not pause_event.is_set():
                if stop_event.is_set():
                    break
                time.sleep(0.1)

            # Synchroniser l'accès aux ressources partagées
            with lock:
                # Ignorer l'événement si la piste est désactivée
                if not active_tracks[track_index]:
                    continue

                # Appliquer la transposition si applicable
                if msg.type in ('note_on', 'note_off'):
                    transposed_note = msg.note + transpose[0]
                    if 0 <= transposed_note <= 127:  # Vérifier que la note reste dans l'échelle MIDI valide
                        msg = msg.copy(note=transposed_note)

                # Envoyer l'événement MIDI
                if not msg.is_meta:
                    outport.send(msg)
                    #print(f"Envoyé (Event_time {event_time}, Piste {track_index + 1}, Canal {msg.channel if hasattr(msg, 'channel') else 'N/A'}): {msg}")

    # Attendre la fin du thread de commande utilisateur
    stop_event.set()
    user_input_thread.join()

    print("Lecture terminée !")

# Programme principal
if __name__ == "__main__":
    # Lister et sélectionner un port MIDI
    #ports = list_ports()
    input_port, output_port = list_and_choose_ports()
    if not input_port and not output_port:
        print("Aucun port MIDI disponible. Assurez-vous que FluidSynth ou un autre périphérique MIDI est actif.")
        exit(1)

    #chosen_port = choose_port(ports)
    #print(f"Port MIDI sélectionné : {chosen_port}")
    #chosen_output_port = choose_port(ports)
    #print(f"Port MIDI de sortie sélectionné : {output_port}")

    #chosen_input_port = choose_port(ports)
    #print(f"Port MIDI d'entrée sélectionné : {input_port}")

    # Chemin du fichier MIDI à lire
    midi_file_path = input("Entrez le chemin du fichier MIDI à lire : ")

    # Lecture synchronisée des pistes avec contrôle interactif
    try:
        play_midi_file_with_control(midi_file_path, output_port)
    except FileNotFoundError:
        print(f"Erreur : Le fichier {midi_file_path} est introuvable.")
    except Exception as e:
        print(f"Une erreur est survenue : {e}")