import socket

def get_fortune(host, port):
    """
    Connect to server and receive a plain text fortune message.
    
    Args:
        host (str): The server hostname or IP address
        port (int): The server port
        
    Returns:
        str: The fortune message
    """
    # Create socket and connect to server
    sock = socket.create_connection((host, port))
    print(f"Connected to {host}:{port}")
    
    try:
        # Receive data until connection closes
        data = bytearray()
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
        
        # Convert received bytes to string
        fortune = data.decode('utf-8')
        return fortune
    
    finally:
        # Ensure socket is closed even if an error occurs
        sock.close()
        print("Connection closed")

def main():
    host = "127.0.0.1"  # Server's IP address
    port = 8888
    
    try:
        # Connect to server and get fortune
        fortune = get_fortune(host, port)
        
        # Print the received fortune
        print("\nFortune message:")
        print(fortune)
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()