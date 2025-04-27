import socket
from Crypto.Cipher import AES
import binascii

def connect_and_decrypt(host, port, key):
    """
    Connect to server, receive IV and ciphertext, decrypt using AES-CBC,
    and return the plaintext message.
    
    Args:
        host (str): The server hostname or IP address
        port (int): The server port
        key (bytes): The AES key as 16 bytes
        
    Returns:
        str: The decrypted message
    """
    # Convert the hex key to bytes if it's provided as a hex string
    if isinstance(key, str):
        key = binascii.unhexlify(key.replace('0x', ''))
    
    # Create socket and connect to server
    sock = socket.create_connection((host, port))
    
    try:
        # Receive the IV (first 16 bytes)
        iv = receive_exact(sock, 16)
        
        # Receive the ciphertext (all remaining data)
        ciphertext = receive_all(sock)
        
        # Create AES cipher in CBC mode with the received IV
        cipher = AES.new(key, AES.MODE_CBC, iv)
        
        # Decrypt the ciphertext
        plaintext = cipher.decrypt(ciphertext)
        
        # Remove padding (PKCS#7)
        padding_length = plaintext[-1]
        plaintext = plaintext[:-padding_length]
        
        # Convert plaintext bytes to string and return
        return plaintext.decode('utf-8')
    
    finally:
        # Ensure socket is closed even if an error occurs
        sock.close()

def receive_exact(sock, num_bytes):
    """
    Receive exactly num_bytes from the socket.
    
    Args:
        sock (socket): Socket object
        num_bytes (int): Number of bytes to receive
        
    Returns:
        bytes: Received data
    """
    data = bytearray()
    bytes_received = 0
    
    while bytes_received < num_bytes:
        chunk = sock.recv(num_bytes - bytes_received)
        
        # If no data is received, the connection was closed
        if not chunk:
            raise ConnectionError("Connection closed before receiving all expected bytes")
        
        data.extend(chunk)
        bytes_received += len(chunk)
    
    return bytes(data)

def receive_all(sock, buffer_size=4096):
    """
    Receive all remaining data from the socket until connection closes.
    
    Args:
        sock (socket): Socket object
        buffer_size (int): Size of buffer for each recv call
        
    Returns:
        bytes: All received data
    """
    data = bytearray()
    
    while True:
        chunk = sock.recv(buffer_size)
        if not chunk:
            break
        data.extend(chunk)
    
    return bytes(data)

def main():
    # Server details
    host = "localhost"  # Replace with your server address
    port = 8888         # Replace with your server port
    
    # AES key (16 bytes = 128 bits)
    key = "00112233445566778899aabbccddeeff"
    
    try:
        # Connect to server, get and decrypt the message
        message = connect_and_decrypt(host, port, key)
        
        # Print the decrypted message
        print("Decrypted message:")
        print(message)
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()