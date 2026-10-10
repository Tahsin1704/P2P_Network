# Peer-to-Peer (P2P) Network Communication and File Sharing

**Course:** CSE 433: Blockchain & Distributed Security Lab

**Department:** Computer Science and Engineering, University of Asia Pacific (UAP)

**Tools & Technologies:** Python 3, TCP Sockets, Multithreading, Tkinter GUI

---

## 1. Project Description

This project is a **Peer-to-Peer (P2P) network** application developed in Python. It allows two or more computers, or two or more windows of the program on the same computer, to communicate **directly** with each other. Using this application, peers can send **text messages** and transfer **files of any type** (images, audio, video, PDF, ZIP, text files, etc.) without using any central server.

The purpose of this project is to understand how computers can communicate with each other without depending on a central server. Through this project, the basic ideas behind distributed systems and blockchain networks are practised in a simple way: how a peer works as both a server and a client using TCP sockets, how two peers identify each other with a handshake, how messages are kept separate using message framing, how any file can be sent safely as raw bytes, and how multithreading lets one peer handle several peers at the same time. 


### Client-Server vs Peer-to-Peer

Most common applications follow the **client-server model**. In this model, every message first goes to a central server, and the server then forwards it to the receiver. The users never talk to each other directly.

```
Client-Server (all messages go through the server):

              Tahsin
                |
     Fahim --- SERVER --- Rafi


Peer-to-Peer (peers connect directly):

              Tahsin
             /      \
        Fahim ------ Rafi
```

The main problem with the client-server model is that the whole system depends on the server. If the server goes offline, becomes slow or fails, no one can communicate. The server is a **single point of failure**.

In a **peer-to-peer model**, there is no central server. Every participant is equal, and each one is called a **peer**. Peers connect to each other directly and exchange data themselves. If one peer leaves the network, the remaining peers can still continue communicating with each other.

### How a Peer Works in This Project

Every running copy of this program is one peer. Each peer performs two roles at the same time:

- **TCP Server:** the peer opens a listening socket on a chosen port and waits for other peers to connect to it.
- **TCP Client:** the peer can start a new connection to another peer by using that peer's IP address and port number.

```
Peer = TCP Server + TCP Client
```

### Project Structure

```
P2P_Network/
├── main.py            # Tkinter GUI (the window you see)
├── p2p_node.py        # Networking: server, client, threads, text and file transfer
├── protocol.py        # Message format: [4-byte length][JSON]
├── requirements.txt   # No external packages needed
├── README.md          # Project documentation
├── downloads/         # Files received from other peers are saved here
└── screenshots/       # Screenshots of the application
```

---

## 2. Requirements

- **Python Version:** Python 3.9 or higher
- **Operating System:** Windows, macOS, or Linux
- **Editor:** VS Code (or any terminal)
- **Network:** Same Wi-Fi / LAN (only needed when using two computers)
- **Dependencies:** Built using only Python standard libraries:
  - `socket`: TCP connections between peers
  - `threading`: Handling multiple peers and file transfers at the same time
  - `json`: Creating and reading protocol messages
  - `struct`: 4-byte message length header (message framing)
  - `tkinter`: Graphical user interface
  - `os`: Saving received files in the `downloads/` folder
  - `uuid`: Creating a unique ID for each peer
  - `queue`: Passing events safely from network threads to the GUI


**No third-party packages are required.** No pip install is needed.
---


## 3. Installation / Setup Instructions

1. **Install Python 3.9 or newer** from <https://www.python.org/downloads/>. On Windows, tick **"Add Python to PATH"** during installation.
2. **Verify Python Installation** by running the following command in Command Prompt / Terminal:
```
   python --version
```
3. **Extract the Project** ZIP file to get the `P2P_Network` folder.
4. **Install Dependencies:** no packages need to be installed. The project uses only Python's built-in libraries, so no `pip install` or virtual environment is needed.

---
## 4. How to Run the Application

Open a terminal inside the `P2P_Network` folder and run:

```
python main.py
```

To run multiple peers on the same computer for testing, open separate terminal windows and launch `python main.py` in each.

The **P2P Network** window opens. The screen has these parts:

| Section | What it does |
|---|---|
| **My Peer** | Your name and port. Default: **Name = Tahsin, Port = 5000**. Buttons: **Start Peer** and **Stop**. |
| **Connect to Another Peer** | Enter another peer's IP and port, then click **Connect**. |
| **Connected Peers** | List of peers you are connected to. Click a name to choose who receives your message/file. |
| **Messages / Events** | Log of everything that happens (green = success, red = error). |
| **Send Text** | Type a message and click **Send**. |
| **Send File** | Click **Choose File & Send** and pick a file. A progress bar shows the transfer. |

Click **Start Peer**. A green line appears:

```
[SUCCESS] Peer started: Tahsin [1362a6dd] listening on port 5000
```

Click **Stop** to turn the peer off and close all its connections.



---

## 5. How to Connect Two Peers

In this example we use two peers:

| Peer | Name | Port |
|---|---|---|
| Peer 1 | Tahsin | 5000 |
| Peer 2 | Fahim | 5001 |

### A) On the same computer

**Start Peer 1 (Tahsin):**
1. Run `python main.py`.
2. Keep **Name: Tahsin** and **Port: 5000**.
3. Click **Start Peer**.

**Start Peer 2 (Fahim):**
1. Open a second terminal window and run `python main.py` again.
2. Change **Name** to `Fahim` and **Port** to `5001`.
3. Click **Start Peer**.

**Connect Fahim to Tahsin:**
1. In Fahim's window, go to **Connect to Another Peer**.
2. Enter **IP:** `127.0.0.1` and **Port:** `5000`.
3. Click **Connect**.

Both windows now show a green message, and each peer appears in the other's **Connected Peers** list:

```
Fahim's list:   → Tahsin [1362a6dd] 127.0.0.1:5000
Tahsin's list:  ← Fahim [a2000a19] 127.0.0.1:5001
```

> Two peers on the same computer must use **different ports**.

### B) On two different computers

1. Connect both computers to the **same Wi-Fi / LAN**.
2. On Tahsin's computer, open Command Prompt and type `ipconfig`. Note the **IPv4 Address**, for example `192.168.0.105`.
   (Linux/macOS: use `ip a` or `ifconfig`.)
3. On Tahsin's computer, start **Tahsin** on port **5000**.
4. On Fahim's computer, start **Fahim** on port **5001**.
5. In Fahim's window, enter **IP:** `192.168.0.105` and **Port:** `5000`, then click **Connect**.

### Sending a text message

1. Click the peer's name in the **Connected Peers** list. The **To:** label shows who will receive the message.
2. Type the message in **Send Text**.
3. Click **Send** or press **Enter**.

```
Tahsin's window:  [MESSAGE] You -> Fahim: Hello Fahim!
Fahim's window:   [MESSAGE] Tahsin -> You: Hello Fahim!
```

---

## 6. How to Transfer Files

1. Select the destination peer from the **Connected Peers** list.
2. Click **Choose File & Send**.
3. Select any file (image `.jpg/.png`, audio `.mp3`, video `.mp4`, `.pdf`, `.zip`, `.txt`, …).
4. The progress bar shows the transfer in both the sender's and the receiver's window.
5. When the transfer is complete, both windows show a green message:

```
Sender:    [SUCCESS] You -> Receiver: File sent: photo.png (78.8 KB)
Receiver:  [SUCCESS] Sender -> You: File received: photo.png (78.8 KB) saved to downloads/
```

6. The receiver automatically saves the file in the **`downloads/`** folder inside its `P2P_Network` folder.
   If a file with the same name already exists, the new one is saved as `photo (1).png`, `photo (2).png`, and so on.

### How the file transfer works

```
Step 1:  Sender  -->  {"type": "file", "sender_id": "...", "sender_name": "...",
                       "filename": "photo.png", "filesize": 80691}
Step 2:  Sender  -->  raw file bytes, 64 KB at a time
Step 3:  Receiver keeps reading until it has exactly 80691 bytes, then saves the file
```


---
## 7. Example screenshots


![alt text](<screenshots/peer stop.png>)

![alt text](<screenshots/all disconnected .png>)

![alt text](<screenshots/sajid disconnected .png>)

![alt text](<screenshots/received tahsin.png>)

![alt text](<screenshots/fahim to tahsin image .png>)

![alt text](<screenshots/video received in sajid .png>)

![alt text](<screenshots/video to sajid.png>)

![alt text](<screenshots/received fahimm image.png>)

![alt text](<screenshots/image to fahim.png>)

![alt text](<screenshots/TM.png>)

![alt text](<screenshots/f-t m.png>)

![alt text](<screenshots/Message s-T.png>)

![alt text](<screenshots/F Message.png>)

![alt text](<screenshots/message t-f.png>)

![alt text](<screenshots/sajid peer.png>)

![alt text](<screenshots/tahsin to sajid.png>)

![alt text](<screenshots/Fahim peer.png>)

![alt text](<screenshots/Tahsin_Connect to fahim.png>)

![alt text](<screenshots/Fahim_start_peer.png>)

![alt text](<screenshots/Tahsin_Peer_Start.png>)

![alt text](<screenshots/Fahim page.png>)

![alt text](<screenshots/Tahsin_page.png>)
---
## Project Demonstration Video Link
 
https://drive.google.com/file/d/1nn_jOri37Zf1EG8b95Qs3Hcl-69ofJ09/view?usp=sharing
