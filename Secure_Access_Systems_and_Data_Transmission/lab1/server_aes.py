import socket
import threading
import os
from Crypto.Cipher import AES
import binascii

# Configuration
HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = 8888
KEY = binascii.unhexlify('00112233445566778899aabbccddeeff')  # AES key as specified

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

def pad_message(message):
    """
    Apply PKCS#7 padding to the message.
    
    Args:
        message (bytes): Message to pad
        
    Returns:
        bytes: Padded message
    """
    block_size = AES.block_size
    padding_length = block_size - (len(message) % block_size)
    padding = bytes([padding_length]) * padding_length
    return message + padding

def encrypt_message(message, key):
    """
    Encrypt a message using AES-CBC mode.
    
    Args:
        message (str): Message to encrypt
        key (bytes): AES key
        
    Returns:
        tuple: (iv, ciphertext)
    """
    # Convert message to bytes if it's a string
    if isinstance(message, str):
        message = message.encode('utf-8')
    
    # Apply padding
    padded_message = pad_message(message)
    
    # Generate random IV
    iv = os.urandom(AES.block_size)
    
    # Create cipher and encrypt
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(padded_message)
    
    return iv, ciphertext

def handle_client(client_socket):
    """
    Handle a client connection.
    
    Args:
        client_socket (socket): Connected client socket
    """
    try:
        # Select a random fortune
        fortune = FORTUNES[os.urandom(1)[0] % len(FORTUNES)]
        print(f"Sending fortune: {fortune}")
        
        # Encrypt the fortune
        iv, ciphertext = encrypt_message(fortune, KEY)
        
        # Send IV followed by ciphertext
        client_socket.sendall(iv)
        client_socket.sendall(ciphertext)
        
    except Exception as e:
        print(f"Error handling client: {e}")
    
    finally:
        # Close the connection
        client_socket.close()

def main():
    """Start the AES server and listen for connections."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((HOST, PORT))
        server.listen(5)
        print(f"[*] Listening on {HOST}:{PORT}")
        
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