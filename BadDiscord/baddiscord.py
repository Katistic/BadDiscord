from PySide2.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,\
QPushButton, QLineEdit, QSizePolicy, QMessageBox, QStyle, QToolBar, QMenu, QWidgetAction

from PySide2.QtCore import Qt
from PySide2.QtGui import QIcon, QWindow, QPalette

from qasync import QEventLoop, QThreadExecutor

import threading

import discord
import asyncio
import aiohttp # Instead of requests in favour of asyncio ability
import time
import json
import uuid
import os

io = None
c = None

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

class LoginMenu(QWidget):
    def switcher(self, nw):
        self.cwidget.hide()

        self.cwidget = nw
        nw.show()

    async def loginUserDetails(self, e, p):
        self.setEnabled(False)

        t = await c.getUserToken(e, p)

        if t != None:
            await self.loginToken(t, False)
        else:
            self.setEnabled(True)

    async def loginToken(self, t, b):
        self.setEnabled(False)

        try:
            await c.login(t, bot=b)
            try:
                id = io.GetId()
                d = io.Read(True, id)

                d["LoginDetails"]["Token"] = t
                d["LoginDetails"]["BotUser"] = b

                io.Write(d, id)

                await discord.Client.connect(c)
            except Exception as e:
                c.Popup(str(e))
                self.setEnabled(True)
        except discord.errors.LoginFailure as e:
            c.Popup("Token is incorrect.")
            self.setEnabled(True)
        except discord.errors.HTTPException as e:
            c.Popup(str(e))
            self.setEnabled(True)

    def setupUserLogin(self):
        ul = QWidget()
        ull = QVBoxLayout()
        ul.setLayout(ull)

        ## Back button

        bbw = QWidget()
        bbwl = QHBoxLayout()
        bbw.setLayout(bbwl)

        bb = QPushButton("<- Go Back")
        bb.setStyleSheet("background-color: #ffffff;")
        spacer = QWidget()

        bbwl.addWidget(bb)
        bbwl.addWidget(spacer)

        bbwl.setStretchFactor(spacer, 5)
        bb.clicked.connect(lambda: self.switcher(self.mm))
        bb.clicked.connect(lambda: c.setFixedSize(450, 150))

        ull.addWidget(bbw)

        ## Detail Fields

        ew = QWidget()
        pw = QWidget()
        ewl = QHBoxLayout()
        pwl = QHBoxLayout()
        ew.setLayout(ewl)
        pw.setLayout(pwl)

        ewl.addWidget(QLabel("Email"))
        pwl.addWidget(QLabel("Password"))

        email = QLineEdit()
        email.setStyleSheet("background-color: #ffffff;")
        passw = QLineEdit()
        passw.setStyleSheet("background-color: #ffffff;")
        dlb = QPushButton("Login")
        dlb.setStyleSheet("background-color: #ffffff;")
        dlb.clicked.connect(lambda: loop.create_task(self.loginUserDetails(email.text(), passw.text())))

        ewl.addWidget(email)
        pwl.addWidget(passw)

        ull.addWidget(ew)
        ull.addWidget(pw)
        ull.addWidget(dlb)

        ## Seperator

        ull.addWidget(QLabel("_______________________________________________________________________"))

        ## Token Login

        tw = QWidget()
        twl = QHBoxLayout()
        tw.setLayout(twl)

        token = QLineEdit()
        token.setStyleSheet("background-color: #ffffff;")
        tlb = QPushButton("Login")
        tlb.setStyleSheet("background-color: #ffffff;")
        tlb.clicked.connect(lambda: loop.create_task(self.loginToken(token.text(), False)))

        twl.addWidget(QLabel("Token"))
        twl.addWidget(token)

        ull.addWidget(tw)
        ull.addWidget(tlb)

        # Align everything to top
        squish = QWidget()
        ull.addWidget(squish)
        ull.setStretchFactor(squish, 100)

        return ul

    def setupBotLogin(self):
        bl = QWidget()
        bll = QVBoxLayout()
        bl.setLayout(bll)

        ## Back button

        bbw = QWidget()
        bbwl = QHBoxLayout()
        bbw.setLayout(bbwl)

        bb = QPushButton("<- Go Back")
        bb.setStyleSheet("background-color: #ffffff;")
        spacer = QWidget()

        bbwl.addWidget(bb)
        bbwl.addWidget(spacer)

        bbwl.setStretchFactor(spacer, 5)
        bb.clicked.connect(lambda: self.switcher(self.mm))
        bb.clicked.connect(lambda: c.setFixedSize(450, 150))

        bll.addWidget(bbw)

        ## Token Login

        tw = QWidget()
        twl = QHBoxLayout()
        tw.setLayout(twl)

        token = QLineEdit()
        token.setStyleSheet("background-color: #ffffff;")
        tlb = QPushButton("Login")
        tlb.setStyleSheet("background-color: #ffffff;")
        tlb.clicked.connect(lambda: loop.create_task(self.loginToken(token.text(), True)))

        twl.addWidget(QLabel("Token"))
        twl.addWidget(token)

        bll.addWidget(tw)
        bll.addWidget(tlb)

        # Align everything to top
        squish = QWidget()
        bll.addWidget(squish)
        bll.setStretchFactor(squish, 5)

        return bl

    def __init__(self):
        super().__init__()

        l = QVBoxLayout()
        self.setLayout(l)

        title = QLabel("Login to BadDiscord")
        title.setAlignment(Qt.AlignHCenter)
        title.setStyleSheet("font: 18pt;")
        l.addWidget(title)

        self.mm = QWidget()
        mml = QVBoxLayout()
        self.mm.setLayout(mml)

        ul = self.setupUserLogin()
        bl = self.setupBotLogin()

        ulb = QPushButton("Login as User")
        blb = QPushButton("Login as Bot")
        mml.addWidget(ulb)

        ulb.setStyleSheet("background-color: #ffffff;")
        blb.setStyleSheet("background-color: #ffffff;")

        mml.addWidget(blb)

        l.addWidget(ul)
        l.addWidget(bl)
        l.addWidget(self.mm)

        ul.hide()
        bl.hide()

        self.cwidget = self.mm

        ulb.clicked.connect(lambda: self.switcher(ul))
        ulb.clicked.connect(lambda: c.setFixedSize(450, 350))

        blb.clicked.connect(lambda: self.switcher(bl))
        blb.clicked.connect(lambda: c.setFixedSize(450, 220))

        # Align everything to top
        squish = QWidget()
        l.addWidget(squish)
        l.setStretchFactor(squish, 5)

        self.show()

class MainApp(QWidget):
    def ScreenChanged(self, screen):
        self.client.setMaximumSize(screen.size())

    def addServerAction(self, text, function, args=[], kwargs={}):
        action = QWidgetAction(self)
        aButton = QPushButton(text)
        aButton.clicked.connect(lambda: function(*args, **kwargs))

        action.setDefaultWidget(aButton)
        self.ServerActions.addAction(action)

    def setupTopBar(self):
        tb = QWidget()
        tbl = QHBoxLayout()
        tb.setLayout(tbl)
        tb.setStyleSheet("border: 3px solid black; background-color: #7289da;")

        tbl.setAlignment(Qt.AlignLeft)

        homeBtn = QPushButton()
        homeBtn.setIcon(self.client.ico)

        saTB = QToolBar()
        self.ServerActions = QMenu()
        self.ServerActions.setTitle("⠀           Home             ⠀")

        saTB.addAction(self.ServerActions.menuAction())

        tbl.addWidget(homeBtn)
        tbl.addWidget(saTB)
        saTB.setStyleSheet("border: 1px solid black;")
        homeBtn.setStyleSheet("border: none;")
        self.ServerActions.setStyleSheet("border: none;")

        return tb

    def __init__(self, parent):
        super().__init__()

        self.client = parent
        parent.maw = self
        parent.l.addWidget(self)

        l = QVBoxLayout()
        self.setLayout(l)
        l.setAlignment(Qt.AlignTop)

        tb = self.setupTopBar()

        l.addWidget(tb)

        parent.setMinimumSize(parent.size())
        parent.setMaximumSize(parent.screen().size())

        parent.screenChanged.connect(self.ScreenChanged)

        parent.hide()
        parent.setWindowFlag(Qt.CustomizeWindowHint)
        parent.setWindowFlag(Qt.WindowMaximizeButtonHint)
        parent.show()

        self.show()

class Client(QWidget, QWindow, discord.Client):
    def __init__(self):
        QWidget.__init__(self)
        QWindow.__init__(self)
        discord.Client.__init__(self)

        self.maw = None
        self.ico = QIcon()
        self.ico.addFile("./Assets/logo.jpg")

    async def on_ready(self):
        print("Logged in as " + self.user.name)

        self.lm.hide()
        del self.lm

        self.setWindowTitle("BadDiscord -- " + self.user.name + " -- Bot User"\
         if self.user.bot else "BadDiscord -- " + self.user.name)

        self.setStyleSheet("background-color: #2c2f33;")
        MainApp(self)

    def Popup(self, text):
        l = QMessageBox()
        l.setText(text)
        l.setWindowTitle("Login Failed")
        l.setIcon(QMessageBox.Warning)
        l.setWindowIcon(self.style().standardIcon(getattr(QStyle, "SP_MessageBoxWarning")))
        l.show()

        self.temp = l

    async def getMFAToken(self, ticket, code):
        payload = {
            "code": code,
            "gift_code_sku_id": None,
            "login_source": None,
            "ticket": ticket
        }

        async with self.bses.post("https://discordapp.com/api/v7/auth/mfa/totp", json=payload) as r:
            r = await r.json()

            if "token" not in r:
                self.Popup(r["message"])
            else:
                return r["token"]

        return None

    async def loginWithMFAToken(self, w, code, ticket):
        w.setEnabled(False)

        token = await self.getMFAToken(ticket, code.text())
        if token == None:
            w.setEnabled(True)
        else:
            w.hide()
            del w

            await self.lm.loginToken(token, False)

    async def mfaKeyGrab(self, ticket):
        w = QWidget()
        l = QVBoxLayout()
        w.setLayout(l)

        label = QLabel("Enter your Two-Factor Auth Code")
        label.setStyleSheet("font: 18pt;")
        code = QLineEdit()
        lb = QPushButton("Login")

        l.addWidget(label)
        l.addWidget(code)
        l.addWidget(lb)

        lb.clicked.connect(lambda: loop.create_task(self.loginWithMFAToken(w, code, ticket)))

        w.show()

    async def getUserToken(self, e, p):
        payload = {
            'email': e,
            'password': p
        }

        async with self.bses.post('https://discordapp.com/api/v7/auth/login', json=payload) as r:
            r = await r.json()

        #await session.close()

            if "token" in r and not "mfa" in r and not r["token"] == None:
                return r["token"]
            elif "errors" in r:
                pt = ""
                for key in r["errors"]:
                    if pt != "": pt += "\n"
                    pt += key.capitalize() + ": " + r["errors"][key]["_errors"][0]["message"] + "."

                self.Popup(pt)
            elif "captcha_key" in r:
                self.Popup("Account with that email does not exist.")
            else:
                await self.mfaKeyGrab(r["ticket"])

        return None

    async def startClient(self):
        self.bses = aiohttp.ClientSession(
            loop=asyncio.get_event_loop(),
            timeout=aiohttp.ClientTimeout(total=1)
        )

        self.l = QVBoxLayout()
        self.setLayout(self.l)

        self.lm = LoginMenu()
        self.l.addWidget(self.lm)
        self.l.setMargin(0)

        self.setFixedSize(450, 150)
        self.setWindowTitle("BadDiscord -- Login")
        self.setWindowIcon(self.ico)
        self.setStyleSheet("background-color: #7289da;")

        self.show()

if __name__ == "__main__":
    app = QApplication()
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    c = Client()

    io = IOManager("configs.json")
    if io.Read() == {}:
        # Write defaults to configs
        io.Write({
            "LoginDetails": {
                "Token": None,
                "BotUser": False,
            }
        })

    # So we don't have to ensure loop is always running,
    # Create task and run forever
    with loop:
        loop.create_task(c.startClient())
        loop.run_forever()

    io.Stop()
