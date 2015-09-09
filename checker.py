# -*- coding: utf-8 -*-
import os
import string
import urllib
import requests
import random
import json
from hashlib import md5
from themis.checker import Server, Result
from time import sleep
from random import randrange
from multiprocessing import Pool

from agents import get_agent

class SampleChecker(Server):

	register_step_err = "Registration step err:  %s"
	login_step_err = "Login step err: %s"
	billing_step_err = "Billing (push) step err: %s"
	validate_step_err = "Validate (pull) step err: %s"
	conn_timeout = os.getenv("SOCKET_TIMEOUT", 10)

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
		return "seriousbank___" + flag

	def new_billing(self):
		bid = self.generate_bid()
		sign = self.generate_flag()
		return {"bid":bid, "sign":sign}



	def get_post_form_headers(self, data=""):
		headers={"User-Agent":get_agent(), #"Mozilla/5.0 (Windows NT 6.3; WOW64; rv:40.0) Gecko/20100101 Firefox/40.0"
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
								timeout=self.conn_timeout,
								allow_redirects=False)

			except requests.ConnectionError as ex:
				self.logger.error(self.register_step_err % unicode(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)
			except requests.HTTPError as ex:
				self.logger.error(self.register_step_err % str(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.MUMBLE, flag_id)
			except requests.Timeout as ex:
				self.logger.error(self.register_step_err % str(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)						
			except Exception as ex:
				self.logger.error(self.register_step_err % str(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)

			if (reg.status_code == 302) and self.check_registration(reg): #( reg.headers.get("location") is not None ):
				try:
					login = s.post(team_host + "/login/", 
									data=acc_data, 
									headers=self.get_post_form_headers(acc_data),
									timeout=self.conn_timeout,
									allow_redirects=False)

				except requests.ConnectionError as ex:
					self.logger.error(self.login_step_err % unicode(ex))
					self.logger.debug(str(ex), exc_info=True)
					return (Result.DOWN, flag_id)
				except requests.HTTPError as ex:
					self.logger.error(self.login_step_err % str(ex))
					self.logger.debug(str(ex), exc_info=True)
					return (Result.MUMBLE, flag_id)
				except requests.Timeout as ex:
					self.logger.error(self.login_step_err % str(ex))
					self.logger.debug(str(ex), exc_info=True)
					return (Result.DOWN, flag_id)						
				except Exception as ex:
					self.logger.error(self.login_step_err % str(ex))
					self.logger.debug(str(ex), exc_info=True)
					return (Result.DOWN, flag_id)

				sid = s.cookies.get("sessionid")

				if (login.status_code == 302) and (sid is not None):
					#print "sid:",sid
					#print "billing"
					try:
						bill = s.post(team_host + "/billing/", 
										data=bill_data, 
										headers=self.get_post_form_headers(bill_data),
										timeout=self.conn_timeout,
										allow_redirects=False)

					except requests.ConnectionError as ex:
						self.logger.error(self.billing_step_err % unicode(ex))
						self.logger.debug(str(ex), exc_info=True)
						return (Result.DOWN, flag_id)
					except requests.HTTPError as ex:
						self.logger.error(self.billing_step_err % str(ex))
						self.logger.debug(str(ex), exc_info=True)
						return (Result.MUMBLE, flag_id)
					except requests.Timeout as ex:
						self.logger.error(self.billing_step_err % str(ex))
						self.logger.debug(str(ex), exc_info=True)
						return (Result.DOWN, flag_id)						
					except Exception as ex:
						self.logger.error(self.billing_step_err % str(ex))
						self.logger.debug(str(ex), exc_info=True)
						return (Result.DOWN, flag_id)

					tid = s.cookies.get("transaction_id")
					tsign = s.cookies.get("transaction_sign")

					if (bill.status_code == 302) and (tid is not None):	
						account["billing"] = billing
						flag_id = {"account": account, "sid":sid, "tid":tid, "tsign": tsign}

						return (Result.UP, self.dumper(flag_id) )

					else:
						self.logger.error(self.billing_step_err % "billing failed")
						#print "billing failed"
						#print bill.text.encode("utf-8")
						return (Result.MUMBLE, flag_id)
				else:
					self.logger.error(self.login_step_err % "login failed")
					#print "login failed"
					#print login.text.encode("utf-8")
					return (Result.MUMBLE, flag_id)
			else:
				self.logger.error(self.register_step_err % "register failed")
				#print "register failed"
				#print reg.text.encode("utf-8")
				return (Result.MUMBLE, flag_id)

	def pull(self, endpoint, flag_id, flag):
		headers={"User-Agent":get_agent(),}#"Mozilla/5.0 (Windows NT 6.3; WOW64; rv:40.0) Gecko/20100101 Firefox/40.0"
		flag_id = self.loader(flag_id)

		team_host = "http://%s:8000" % endpoint
		billing_cell = "/billing/%s/" % flag_id["account"]["username"]
		validate_cell = "/validate/%s/" % flag_id["tid"]

		with requests.Session() as s:
			s.cookies.set("sessionid", flag_id["sid"])
			s.cookies.set("transaction_id", flag_id["tid"])
			
			try:

				check = s.get(team_host + billing_cell,
								timeout=self.conn_timeout,
								headers=headers)

			except requests.ConnectionError as ex:
				self.logger.error(self.validate_step_err % unicode(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)
			except requests.HTTPError as ex:
				self.logger.error(self.validate_step_err % str(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.MUMBLE, flag_id)
			except requests.Timeout as ex:
				self.logger.error(self.validate_step_err % str(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)						
			except Exception as ex:
				self.logger.error(self.validate_step_err % str(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)

			s.cookies.set("transaction_sign", flag_id["tsign"])

			try:

				validate = s.get(team_host + validate_cell,
									timeout=self.conn_timeout,
									headers=headers)

			except requests.ConnectionError as ex:
				self.logger.error(self.validate_step_err % unicode(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)
			except requests.HTTPError as ex:
				self.logger.error(self.validate_step_err % str(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.MUMBLE, flag_id)
			except requests.Timeout as ex:
				self.logger.error(self.validate_step_err % str(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)						
			except Exception as ex:
				self.logger.error(self.validate_step_err % str(ex))
				self.logger.debug(str(ex), exc_info=True)
				return (Result.DOWN, flag_id)

			if (check.status_code == 200) and (validate.status_code == 200):
				flag_stat = s.cookies.get("valid")
				if flag_stat is None:
					return Result.MUMBLE

				elif flag_stat == "True":

					if flag_id["account"]["billing"]["sign"] == check.text.replace('\n','').replace('\r',''):
						return Result.UP
					else:
						return Result.CORRUPT
				else:
					Result.MUMBLE
			else:
				return Result.MUMBLE

def check_flag(checker, flag_id):
	print "Pull data: ", flag_id.decode('base64')
	print "Pulling return is: ", checker.pull("localhost", flag_id, "")

def testrun():
	checker = SampleChecker()
	ids = []
	for x in xrange(10):
		result, flag_id = checker.push("localhost", "", "")
		if (result == Result.UP) and (flag_id is not None):
			ids.append(flag_id)
			print "Push return is", result, " data: ", flag_id.decode('base64'), "\nData len: ", len(flag_id)
			#print "Pulling return is: ", checker.pull("localhost", flag_id, "")
			check_flag(checker, flag_id)
			check_flag(checker, random.choice(ids))

def runmultiple(function, instances):
	pool = Pool(8)
	for x in xrange(instances):
		pool.apply_async(function)
	while True:
		pass

if __name__ == '__main__':
	#runmultiple(testrun, 8)
	checker = SampleChecker()
	checker.run()