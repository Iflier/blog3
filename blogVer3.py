# -*-coding: utf-8 -*-
"""
Level : Fun
Dec:
Created on : 2017.07.27
Modified on : 2017.07.28
Author : Iflier
"""
print(__doc__)

import time
import datetime
import os.path
import redis
import MySQLdb
from tornado import web
import tornado.httpserver
from tornado.web import url
from tornado.options import define, options, parse_command_line
from pymongo import MongoClient

define("port", default=9000, help="Runing on the given port.", type=int)
client = MongoClient("mongodb://localhost:27000")
clientCache = redis.StrictRedis(host='localhost', port=6379, db=0, password='56789app')
conn = MySQLdb.connect(host="localhost", db="userCount", read_default_file="my.cnf")

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            url(r'/', EnterHandler, name='enterPoint'),
            url(r'/login', LoginHandler, dict(database=conn), name="login"),
            web.URLSpec(r'/register', RegisterHandler, dict(database=conn), name="register"),
            url('/welcome', WelcomeHandler, dict(databaseCache=clientCache, databaseMessages=client), name="welcome"),
            url('/help', HelpHandler, name="help"),
            url('/logout', LogoutHandler, name="logout")
        ]
        settings = {
            "static_path": os.path.join(os.path.dirname(__file__), "static"),
            "template_path": os.path.join(os.path.dirname(__file__), "templates"),
            'xsrf_cookies': True,
            'debug': True,
            "cookie_secret": 'a7b8e385-86b9-4605-a09d-15a14cac9cba',
            "login_url": '/login',
            "static_url_prefix": "/static/",
        }
        tornado.web.Application.__init__(self, handlers=handlers, **settings)


class BaseHandler(tornado.web.RequestHandler):
    """"Handler的基类"""
    def write_error(self, status_code, **kwargs):
        if status_code == 404:
            self.render('404.html')
        elif status_code == 500:
            self.render('500.html')
        elif status_code == 405:
            self.render("verboseNotAllowed.html")            
        else:
            self.write("Error: {0}".format(status_code))


class EnterHandler(BaseHandler):
    def get_current_user(self):
        # print("Type of get_secure_cookie: {0}".format(self.get_secure_cookie("username")))
        # bytes str
        return self.get_secure_cookie("username")

    @tornado.web.authenticated
    def get(self):
        self.redirect("/welcome")


class RegisterHandler(BaseHandler):
    def initialize(self, database):
        self.db = database

    def prepare(self):
        # Before any request
        self.cursor = self.db.cursor()

    def get(self):
        self.render("register.html")
    
    def post(self):
        username = self.get_argument("username", None)
        password = self.get_argument("password", None)
        if username is None or password is None:
            self.render("register.html")
        else:
            sql = "SELECT * FROM blogusers WHERE username=%s"
            # sql = "SELECT username FROM blogusers WHERE username=%s"
            result = self.cursor.execute(sql, (username,))
            print("Select result: {0}".format(result))
            if bool(result):
                self.write('<html><body><a href="%s">Register-->></a></body></html' % (self.reverse_url('register')))
            else:
                sql = "INSERT INTO blogusers(username, password) VALUES(%s, %s)"
                result = self.cursor.execute(sql, (username, password))
                self.db.commit()
                print("Result of execute db: {0}".format(result))
                if result:
                    self.set_secure_cookie("username", username)
                    self.redirect('/welcome')
                else:
                    self.render("500.html")

    def on_finish(self):
        self.cursor.close()


class LoginHandler(BaseHandler):
    def initialize(self, database):
        self.db = database
    
    def prepare(self):
        self.cursor = self.db.cursor()

    def get(self):
        self.render("login.html")
    
    def post(self):
        username = self.get_argument("username", None)
        password = self.get_argument("password", None)
        print("Type of username: {}".format(type(username)))
        if username is None or password is None:
			self.render("login.html")
        else:
            sql = "SELECT * FROM blogusers WHERE username=%s AND password=%s"
            result = self.cursor.execute(sql, (username, password))
            print("Result from db: {0}".format(result))
            if result:
                self.set_secure_cookie("username", username, expires=time.time() + 30 * 60)
                self.redirect("/welcome", permanent=False)
            else:
                self.redirect("/register", permanent=False)
    
    def on_finish(self):
        print("[INFO] Closeing DB cursor ...")
        self.cursor.close()


class WelcomeHandler(BaseHandler):
    """Welcome page"""
    def initialize(self, databaseCache, databaseMessages):
        self.cacheDB = databaseCache
        self.messagesDB = databaseMessages
    
    def get(self):
        kwargs = {}
        username = self.get_secure_cookie("username", None)  # bytes str
        if username:
            print("Current user: {}".format(username))
            # if self.cacheDB.setnx("visitorCount", 1):                
            if self.cacheDB.setnx("visitorCount", 1) is True:
                times = 1
            else:
                times = self.cacheDB.incr("visitorCount", amount=1)
            # username = "Anonymous" if username is None else username
            print("Current visitors：{0:>03,d}".format(times))
            userAndMessages = {}
            allDatebaseNames = self.messagesDB.database_names()
            for databaseName in allDatebaseNames:
                messagesList = []
                for doc in self.messagesDB[databaseName].message.find(projection={"_id": False}).sort([("date", 1)]):
                    if doc:
                        messagesList.append(doc)
                    else:
                        pass
                userAndMessages[databaseName] = messagesList
                # print(messagesList)
            kwargs["times"] = times
            kwargs["username"] = username.decode(encoding='utf-8')
            kwargs["userAndMessages"] = userAndMessages
            self.render("welcome.html", **kwargs)
        else:
            self.redirect("/login")

    def post(self):
        username = self.get_secure_cookie("username", None)
        if username is None:
            self.redirect("/login")
        else:
            assert isinstance(username, bytes)
            username = username.decode(encoding='utf-8')
            message = self.get_argument("leaveMessage", default=None)
            if message:
                everyUserDB = self.messagesDB[username]
                date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                insertedResult = everyUserDB.message.insert_one({"date": date, "message": message})
                print("Inserted ID: {0}".format(insertedResult.inserted_id))
                self.redirect("/welcome")
            else:
                self.redirect("/welcome")


class HelpHandler(BaseHandler):
    def get(self):
        self.render("help.html")


class LogoutHandler(BaseHandler):
    """用户登出"""
    def get(self):
        self.clear_cookie("username")
        # self.set_secure_cookie("username", None)
        self.redirect("/login")


if __name__ == "__main__":
    parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application(), xheaders=True)
    http_server.bind(options.port, reuse_port=False)  # OS: Windows10, reuse_port is unavailable
    http_server.start()
    tornado.ioloop.IOLoop.current().start()
