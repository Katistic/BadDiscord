from PySide2.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton,\
QLineEdit

from PySide2.QtCore import Qt

import threading

import discord
import asyncio
import requests
import time
import json
import uuid
import os

bot = None

class IOManager: ## Manages reading and writing data to files.
    def __init__(self, file, start=True, jtype=True, binary=False):
        '''
        file:
            type, string
            Path to file to iomanage
        start:
            -- OPTIONAL --
            type, boolean
            default, True
            Start operations thread on creation
        jtype:
            -- OPTIONAL --
            type, boolean
            default, True
            File is json database
        binary:
            -- OPTIONAL --
            type, boolean
            default, False
            Open file in binary read/write mode
        '''

        self.Ops = [] # Operations
        self.Out = {} # Outputs
        self.Reserved = [] # Reserved keys for operations

        self.stopthread = False # Should stop operations thread
        self.stopped = True # Is operations thread stopped
        self.thread = None # Operation thread object
        self.file = file # File to read/write

        ## Assigning open params to class

        if binary: # Can not be json type and binary read/write
            self.jtype = False
        else:
            self.jtype = jtype

        self.binary = binary

        # Create file if it doesn't already exist
        if not os.path.isfile(file):
            with open(file, "w+") as file:
                if jtype:
                    file.write("{}")

        if start: # start if kwarg start is True
            self.Start()

    def GetId(self): # Class to get a probably unique key
        return uuid.uuid4()

    def Read(self, waitforwrite=False, id=None): # Handles creating read operations
        '''
        waitforwrite:
            -- OPTIONAL --
            type, boolean
            default, False
            Operations thread should wait for write process same id kwarg
            Requires id kwarg to be set
        id:
            -- OPTIONAL --
            type, uuid4
            default, None
            ID to identify this operation
        '''

        if not waitforwrite:
            if id == None: id = uuid.uuid4() # get uuid if none passed
            self.Ops.append({"type": "r", "wfw": False, "id": id}) # Add operation to list
        else: # Wait for next write with same id
            if id == None: # waitforwrite requires id
                return None

            # Check for duplicate ids

            for x in self.Ops:
                if x["id"] == id:
                    return None

            if id in self.Reserved:
                return None

            # Reserve id
            # Add operation to list
            self.Reserved.append(id)
            self.Ops.append({"type": "r", "wfw": True, "id": id})

        while not id in self.Out: # Wait for read operation to complete
            time.sleep(.01)

        result = self.Out[id] # Get results
        del self.Out[id] # Delete results from output
        return result["data"] # return results

    def Write(self, nd, id=None):
        '''
        nd:
            type, string/bytes
            New data to write to file
        id:
            -- OPTIONAL --
            type, uuid
            default, None
            ID to identify this operation
        '''

        self.Ops.append({"type": "w", "d": nd, "id": id}) # Add write operation to list

    def Start(self): # Start operations thread
        if self.stopped: # Start only if thread not running
            self.stopthread = False # Reset stopthread to avoid immediate stoppage

            # Create thread and start
            self.thread = threading.Thread(target=self.ThreadFunc)
            self.thread.start()

    def Stop(self): # Stop operations thread
        if not self.stopthread: # Stop thread only if not already stopping
            if not self.stopped: # Stop thread only if thread running
                self.stopthread = True

    def isStopped(self): # Test if operations thread not running
        return self.stopped

    def ThreadFunc(self): # Operations function
        self.stopped = False # Reset stopped attr

        # Read/write type, binary or not
        t = None
        if self.binary:
            t = "b"
        else:
            t = ""

        # Main loop
        while not self.stopthread: # Test for stop attr
            if len(self.Ops) > 0: # Test for new operations

                # Get next operation
                Next = self.Ops[0]
                del self.Ops[0]

                # Open file as 'type' (read/write) + t (binary/text)
                with open(self.file, Next["type"]+t) as file:
                    id = Next["id"] # Operation ID

                    if Next["type"] == "r": # If is read operation

                        # Use json.load if in json mode
                        if self.jtype:
                            d = json.load(file)
                        else:
                            d = file.read()

                        # Put data in output
                        self.Out[id] = {"data": d, "id": id}

                        if Next["wfw"]: # Test if read operation is wait-for-write
                             # Wait for write loop
                            while not self.stopthread: # Test for stop attr

                                # Search for write operation with same id
                                op = None
                                for op in self.Ops:
                                    if op["id"] == id:
                                        break

                                # If no write operation, wait and restart loop
                                if op == None:
                                    time.sleep(.1)
                                    continue

                                self.Reserved.remove(id) # Remove reserved id
                                self.Ops.remove(op) # Remove write operation from list
                                self.Ops.insert(0, op) # Place write operation first
                                break # Break wfw loop
                            continue # Continue to main loop start

                    elif Next["type"] == "w": # If is write operation

                        # Use json.dump if in json mode
                        if self.jtype:
                            json.dump(Next["d"], file, indent=4)
                        else:
                            file.write(Next["d"])

            else: # If no operations, wait.
                time.sleep(.1)

        self.stopped = True # Set operation thread as stopped

class Client(discord.Client):
    def __init__(self):
        super().__init__()

        self.io = IOManager("configs.json")
        if self.io.Read() == {}:
            # Write defaults to configs
            self.io.Write({
                "LoginDetails": {
                    "Token": None,
                    "BotUser": False,
                    "Email": None,
                    "Password": None
                }
            })

        self.botThread = None

    # Event Handling

    async def on_ready(self):
        print("Ready")

    # Setups

    def setUserEmail(self, e):
        id = self.io.GetId()
        fd = self.io.Read(waitforwrite=True, id=id)
        fd['LoginDetails']['Email'] = e
        self.io.Write(fd, id)

    def setUserPassword(self, p):
        id = self.io.GetId()
        fd = self.io.Read(waitforwrite=True, id=id)
        fd['LoginDetails']['Password'] = p
        self.io.Write(fd, id)

    def setBotUser(self, b):
        id = self.io.GetId()
        fd = self.io.Read(waitforwrite=True, id=id)
        fd['LoginDetails']['BotUser'] = b
        self.io.Write(fd, id)

    def setToken(self, t):
        id = self.io.GetId()
        fd = self.io.Read(waitforwrite=True, id=id)
        fd['LoginDetails']['Token'] = t
        self.io.Write(fd, id)

    def uLogin(self):
        d = self.io.Read()

        payload = {
            'email': d["LoginDetails"]["Email"],
            'password': d["LoginDetails"]["Password"]
        }

        r = requests.post('https://discordapp.com/api/v7/auth/login', json=payload)
        if r.status_code == 400:
            raise discord.errors.LoginFailure('Improper credentials have been passed.')
        elif r.status_code != 200:
            r.status = r.status_code
            raise discord.errors.HTTPException(r, r.reason)

        r = r.json()
        if r['token'] != None:
            self.setToken(r['token'])
            self.sRun()
        else:
            raise Exception("MFA accounts are not supported.")

    def sRun(self):
        d = self.io.Read()["LoginDetails"]
        t = d['Token']
        b = d['BotUser']

        try:
            self.run(t, bot=b)
        except discord.errors.LoginFailure as e:
            if d['Email'] != None and d['Password'] != None and d["BotUser"] == True:
                self.uLogin()
            else:
                raise discord.errors.LoginFailure(e)
        except discord.errors.HTTPException as e:
            raise Exception(e)

## Menu Definitions ##

class UpdaterWindow:
    pass # Will do when first release hits

class LoginMenu(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('BadDiscord -- Login')

        rl = QVBoxLayout()
        self.setLayout(rl)

        self.status = QLabel()
        self.status.setAlignment(Qt.AlignHCenter)

        rl.addWidget(self.status)

        self.buttHolder = QWidget()
        bl = QVBoxLayout()
        self.buttHolder.setLayout(bl)

        botButton = QPushButton("Bot Login")
        userButton = QPushButton("User Login")
        regButton = QPushButton("User Register")

        bl.addWidget(botButton)
        bl.addWidget(userButton)
        bl.addWidget(QLabel("____________________________________________________________________"))
        bl.addWidget(regButton)

        botButton.clicked.connect(self.botLoginF)
        userButton.clicked.connect(self.userLoginF)

        rl.addWidget(self.buttHolder)
        self.show()

        self.setFixedSize(450, 190)

        self.botLogin = QWidget()
        bll = QVBoxLayout()
        self.botLogin.setLayout(bll)

        self.bToken = QLineEdit()
        self.bLoginButton = QPushButton("Login")

        self.bLoginButton.clicked.connect(lambda: self.doTokenLogin(self.bToken.text(), True))

        bll.addWidget(self.bToken)
        bll.addWidget(self.bLoginButton)
        self.botLogin.hide()

        rl.addWidget(self.botLogin)

        self.userLogin = QWidget()
        ull = QVBoxLayout()
        self.userLogin.setLayout(ull)

        self.uEmail = QLineEdit()
        self.uPass = QLineEdit()
        self.uuLogin = QPushButton("Login")
        self.uToken = QLineEdit()
        self.utLogin = QPushButton("Login")

        self.utLogin.clicked.connect(lambda: self.doTokenLogin(self.uToken.text(), False))
        self.uuLogin.clicked.connect(self.doEPLogin)

        ull.addWidget(self.uEmail)
        ull.addWidget(self.uPass)
        ull.addWidget(self.uuLogin)
        ull.addWidget(QLabel("____________________________________________________________________"))
        ull.addWidget(self.uToken)
        ull.addWidget(self.utLogin)
        self.userLogin.hide()

        rl.addWidget(self.userLogin)

    def doTokenLogin(self, t, b):
        bot.setBotUser(b)
        bot.setToken(t)

        if bot.botThread == None or not bot.botThread.is_alive():
            asyncio.set_event_loop(asyncio.new_event_loop())
            bot.botThread = threading.Thread(target = bot.sRun)
            bot.botThread.daemon = True
            bot.botThread.start()

            self.status.setText("Connecting to discord...")
            print("Connecting to discord...")
        else:
            self.status.setText("Client is already running! Please wait...")
            print("Client is already running!")

    def doEPLogin(self):
        bot.setBotUser(False)
        bot.setUserEmail(self.uEmail.text())
        bot.setUserPassword(self.uPass.text())

        if bot.botThread == None or not bot.botThread.is_alive():
            asyncio.set_event_loop(asyncio.new_event_loop())
            bot.botThread = threading.Thread(target = bot.uLogin)
            bot.botThread.daemon = True
            bot.botThread.start()

            self.status.setText("Connecting to discord...")
            print("Connecting to discord...")
        else:
            self.status.setText("Client is already running! Please wait...")
            print("Client is already running!")

    def botLoginF(self):
        self.setFixedSize(450, 150)
        self.setMinimumSize(450, 150)

        self.buttHolder.hide()
        self.botLogin.show()

    def userLoginF(self):
        self.setFixedSize(450, 260)
        self.setMinimumSize(450, 260)

        self.buttHolder.hide()
        self.userLogin.show()

class MainWindow:
    pass


if __name__ == "__main__":
    bot = Client()

    app = QApplication()
    LM = LoginMenu()
    app.exec_()

    bot.io.Stop()
