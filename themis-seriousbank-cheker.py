# -*- coding: utf-8 -*-
import string
import urllib
import requests
import random
import json
from hashlib import md5
from themis.checker import Server, Result
from time import sleep
from random import randrange


class SampleChecker(Server):
	def dumper(self, obj):
		return json.dumps(obj).encode('base64').rstrip("\n")

	def loader(self, obj):
		return json.loads(obj.decode('base64'))



	def randomstr(self, seed, n):
		return ''.join(random.choice(seed) for i in xrange(n))

	def new_account(self):
		name = self.randomstr(string.lowercase + string.uppercase, 15)
		password = self.randomstr(string.lowercase + string.uppercase + string.digits, 30)
		return {"username":name, "password":password}



	def generate_bid(self):
		return str(random.randint(0, 100400))

	def generate_flag(self):
		m = md5()
		m.update(str(random.randint(0, 10000000)))
		flag = m.hexdigest() + '='
		return flag

	def new_billing(self):
		bid = self.generate_bid()
		sign = self.generate_flag()
		return {"bid":bid, "sign":sign}



	def get_post_form_headers(self, data=""):
		headers={"User-Agent":"Mozilla/5.0 (Windows NT 6.3; WOW64; rv:40.0) Gecko/20100101 Firefox/40.0",
				"Content-Type":"application/x-www-form-urlencoded",
				"Content-Length": str(len(data))}
		return headers

	def check_registration(self, response):
		return True if ( response.headers.get("location") is not None ) \
					and ( "/login/" in response.headers.get("location") ) \
					else False

	def push(self, endpoint, flag_id, flag):

		flag_id = None

		account = self.new_account()
		acc_data = urllib.urlencode(account)#{"username":account["username"] , "password":account["password"]})
		#print acc_data

		billing = self.new_billing()
		bill_data = urllib.urlencode(billing)#{"bid":billing["bid"],"sign":billing["sign"]})
		#print bill_data

		team_host = "http://%s:8000" % endpoint

		with requests.Session() as s:
			try:
				reg = s.post(team_host + "/register/", 
								data=acc_data, 
								headers=self.get_post_form_headers(acc_data),
								allow_redirects=False)
			except Exception as ex:
				self.logger.error('Failed connect to the service')
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)

			if (reg.status_code == 302) and self.check_registration(reg): #( reg.headers.get("location") is not None ):
				try:
					login = s.post(team_host + "/login/", 
									data=acc_data, 
									headers=self.get_post_form_headers(acc_data), 
									allow_redirects=False)
				except Exception as ex:
					self.logger.error('Failed connect to the service')
					self.logger.debug(str(ex), exc_info=True)
					return (Result.DOWN, flag_id)

				sid = s.cookies.get("sessionid")

				if (login.status_code == 302) and (sid is not None):
					#print "sid:",sid
					#print "billing"
					try:
						bill = s.post(team_host + "/billing/", 
										data=bill_data, 
										headers=self.get_post_form_headers(bill_data))
					except Exception as ex:
						self.logger.error('Failed connect to the service')
						self.logger.debug(str(ex), exc_info=True)
						return (Result.DOWN, flag_id)

					tid = s.cookies.get("accepted_transaction")

					if (bill.status_code == 200) and (tid is not None):	
						#print "flag_id", tid
						account["billing"] = billing
						flag_id = {"account": account, "sid":sid, "tid":tid}

						return (Result.UP, self.dumper(flag_id) )

					else:
						self.logger.error("billing failed")
						#print "billing failed"
						#print bill.text.encode("utf-8")
						return (Result.MUMBLE, flag_id)
				else:
					self.logger.error("login failed")
					#print "login failed"
					#print login.text.encode("utf-8")
					return (Result.MUMBLE, flag_id)
			else:
				self.logger.error("register failed")
				#print "register failed"
				#print reg.text.encode("utf-8")
				return (Result.MUMBLE, flag_id)

	def pull(self, endpoint, flag_id, flag):
		headers={"User-Agent":"Mozilla/5.0 (Windows NT 6.3; WOW64; rv:40.0) Gecko/20100101 Firefox/40.0",}
		flag_id = self.loader(flag_id)

		team_host = "http://%s:8000" % endpoint
		cell = "/billing/%s/" % flag_id["account"]["username"]

		with requests.Session() as s:
			s.cookies.set("sessionid", flag_id["sid"])
			s.cookies.set("accepted_transaction", flag_id["tid"])
			valid = s.get(team_host + cell, headers=headers)

			if valid.status_code == 200:
				if flag_id["account"]["billing"]["sign"] == valid.text:
					return Result.UP
				else:
					return Result.CORRUPT
			else:
				return Result.MUMBLE

def testrun():
	checker = SampleChecker()
	for x in xrange(10):
		result, flag_id = checker.push("localhost", "", "")
		if (result == Result.UP) and (flag_id is not None):
			print "Push return is", result, " data: ", flag_id.decode('base64')
			print "Pulling return is: ", checker.pull("localhost", flag_id, "")

if __name__ == '__main__':
	checker = SampleChecker()
	checker.run()