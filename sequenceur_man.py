import mido
import time
from threading import Thread, Lock
from collections import deque

# Classe pour gérer les impulsions de la manivelle
class CrankClock:
    def __init__(self, max_impulses=10):
        self.impulse_times = deque(maxlen=max_impulses)
        self.lock = Lock()
        # Ajouter des impulsions fictives pour éviter l'attente initiale
        current_time = time.time()
        self.impulse_times.append(current_time - 0.5)  # Impulsion il y a 0.5s
        self.impulse_times.append(current_time)       # Impulsion actuelle

    def register_impulse(self):
        """Enregistre une impulsion de la manivelle."""
        with self.lock:
            self.impulse_times.append(time.time())

    def get_interval(self):
        """Retourne l'intervalle moyen entre les impulsions."""
        with self.lock:
            if len(self.impulse_times) < 2:
                return None  # Pas assez d'impulsions
            intervals = [
                self.impulse_times[i] - self.impulse_times[i - 1]
                for i in range(1, len(self.impulse_times))
            ]
            return sum(intervals) / len(intervals)

    def ticks_to_seconds(self, ticks, tempo, ticks_per_beat):
        """Convertit les ticks MIDI en temps basé sur les impulsions."""
        interval = self.get_interval()
        if interval is None:
            return None  # Retourner None si aucune impulsion n'est disponible
        # Calcul basé sur l'intervalle moyen des impulsions
        seconds_per_beat = interval * (tempo / 1_000_000)
        return ticks * seconds_per_beat / ticks_per_beat

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

# Envoyer une commande PANIC pour arrêter toutes les notes
def send_panic(outport):
    for channel in range(16):
        outport.send(mido.Message('control_change', channel=channel, control=120, value=0))  # All Sound Off
        outport.send(mido.Message('control_change', channel=channel, control=123, value=0))  # All Notes Off
    print("Commande PANIC envoyée.")

# Lecture des pistes avec contrôle interactif basé sur les impulsions
def play_midi_file_with_crank_control(midi_file_path, output_port, crank_clock):
    midi_file = mido.MidiFile(midi_file_path)
    tempo = 500000  # Valeur par défaut (120 BPM)
    ticks_per_beat = midi_file.ticks_per_beat

    print(f"Lecture du fichier MIDI : {midi_file_path}")
    print(f"Nombre de pistes : {len(midi_file.tracks)}")

    with mido.open_output(output_port) as outport:
        print(f"Envoi des notes au port MIDI : {output_port}")

        tracks_events = []
        for i, track in enumerate(midi_file.tracks):
            time_absolute = 0
            for msg in track:
                time_absolute += msg.time
                if msg.is_meta and msg.type == 'set_tempo':
                    tempo = msg.tempo
                else:
                    tracks_events.append((time_absolute, msg))

        tracks_events.sort(key=lambda x: x[0])

        last_event_time = 0
        for event_time, msg in tracks_events:
            max_wait = 5.0  # Temps d'attente maximum en secondes
            start_wait = time.time()

            while True:
                wait_time = crank_clock.ticks_to_seconds(event_time - last_event_time, tempo, ticks_per_beat)
                if wait_time is not None and wait_time <= 0:
                    break  # Passe à l'événement suivant si le temps d'attente est écoulé
                elif wait_time is None:
                    print("En attente des premières impulsions...")
                    time.sleep(0.1)  # Attendre les impulsions
                else:
                    time.sleep(wait_time)  # Attendre le temps simulé

                # Vérifier le temps maximum d'attente
                if time.time() - start_wait > max_wait:
                    print("Temps d'attente dépassé, continuation forcée.")
                    break

            last_event_time = event_time

            if not msg.is_meta:
                outport.send(msg)

    print("Lecture terminée.")

# Simulation des impulsions de la manivelle
def simulate_crank(clock, interval=0.5):
    """Thread pour simuler les impulsions."""
    while True:
        #clock.register_impulse()
        #print(f"Impulsion simulée à {time.time():.2f}")  # Ajouter un message pour chaque impulsion
        time.sleep(interval)

# Programme principal
if __name__ == "__main__":
    ports = list_ports()
    if not ports:
        print("Aucun port MIDI disponible.")
        exit(1)

    chosen_port = choose_port(ports)
    print(f"Port MIDI sélectionné : {chosen_port}")

    midi_file_path = input("Entrez le chemin du fichier MIDI à lire : ")

    # Instancier l'horloge de la manivelle
    crank_clock = CrankClock()

    # Simuler les impulsions dans un autre thread
    simulation_interval = float(input("Entrez l'intervalle simulé entre impulsions (en secondes, ex. 0.5) : "))
    Thread(target=simulate_crank, args=(crank_clock, simulation_interval), daemon=True).start()

    # Lecture synchronisée
    try:
        play_midi_file_with_crank_control(midi_file_path, chosen_port, crank_clock)
    except FileNotFoundError:
        print(f"Erreur : Le fichier {midi_file_path} est introuvable.")
    except Exception as e:
        print(f"Une erreur est survenue : {e}")
