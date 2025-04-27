import socket
import threading
import random
import os

# Configuration
HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = 8888

# List of sample fortunes/messages
FORTUNES = [
    "The fortune you seek is in another cookie.",
    "A foolish man listens to his heart. A wise man listens to cookies.",
    "You will receive a fortune cookie.",
    "Some fortune cookies contain no fortune.",
    "Today is your day to declare your independence. Don't let anyone tell you otherwise.",
    "The greatest danger could be your stupidity.",
    "Flattery will go far tonight.",
    "Help! I'm being held prisoner in a fortune cookie factory!",
    "It's about time I got out of that cookie.",
    "Never forget a friend. Especially if he owes you.",
    "You will receive a beautiful, smart, and loving pet soon.",
    "Courage is not simply one of the virtues, but the form of every virtue at the testing point.",
    "The early bird gets the worm, but the second mouse gets the cheese."
]

def handle_client(client_socket):
    """
    Handle a client connection - send a plain text fortune.
    
    Args:
        client_socket (socket): Connected client socket
    """
    try:
        # Select a random fortune
        fortune = FORTUNES[random.randint(0, len(FORTUNES) - 1)]
        print(f"Sending fortune: {fortune}")
        
        # Send fortune as plain text
        client_socket.sendall(fortune.encode('utf-8'))
        
    except Exception as e:
        print(f"Error handling client: {e}")
    
    finally:
        # Close the connection
        client_socket.close()

def main():
    """Start the plain text fortune server and listen for connections."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((HOST, PORT))
        server.listen(5)
        print(f"[*] Plain text fortune server listening on {HOST}:{PORT}")
        
        while True:
            client, addr = server.accept()
            print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")
            
            # Handle each client in a new thread
            client_handler = threading.Thread(target=handle_client, args=(client,))
            client_handler.daemon = True
            client_handler.start()
            
    except KeyboardInterrupt:
        print("\n[*] Shutting down server")
    
    except Exception as e:
        print(f"Server error: {e}")
    
    finally:
        server.close()

if __name__ == "__main__":
    main()