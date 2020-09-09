"""
Controls R&S NGM20x power supply remotely without using NI-VISA's godawful API.
"""

import socket, struct, time, datetime

SCK_BUFFSZ = 4096

class RSNGM20xPowerSupply(object):
	# Zero data for channel current offsets.  Channels are 1/2  (only 2 for NGM202)
	ch_zeroes = [None, 0, 0]  
	
	# Accumulated figures in femto amphours (unlimited maximum integer)
	ah_total = 0
	wh_total = 0
	nsamp = 0
	tlast = 0

	def __init__(self, ipaddr, port):
		self.fparser = struct.Struct("<ff") # Create LE-float parser
		
		self.sck = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sck.connect((ipaddr, port))
		self.sck.settimeout(1.0)
		self.command_no_response("\r\n\r\n\r\n")  # Flush buffers
		self.command_no_response("*RST")  # Reset
		time.sleep(0.5)
		
		print("Connected to: %s" % str(self.query('*IDN?'), encoding='ascii').strip())
	
	def command_no_response(self, cmd):
		self.sck.send(bytes(cmd + "\r\n", encoding='ascii'))
	
	def query(self, cmd):
		self.sck.send(bytes(cmd + "\r\n", encoding='ascii'))
		return self.sck.recv(SCK_BUFFSZ)
	
	def continue_socket_recv(self):
		return self.sck.recv(SCK_BUFFSZ)
	
	def sync_datetime(self):
		now = datetime.datetime.now()
		print("Syncing instrument to: ", now)
		
		self.command_no_response("SYST:DATE %d, %d, %d" % (now.day, now.month, now.year))
		self.command_no_response("SYST:TIME %d, %d, %d" % (now.hour, now.minute, now.second))
	
	def set_output_param(self, ch, volt, curr):
		self.command_no_response("INST OUT%d" % ch)
		self.command_no_response("VOLT %3.3f" % volt)
		self.command_no_response("CURR %3.3f" % curr)
	
	def output_enable(self, ch, state):
		self.command_no_response("INST OUT%d" % ch)
		
		if state:
			self.command_no_response("OUTP:STATE 1")
		else:
			self.command_no_response("OUTP:STATE 0")
	
	def output_off_zero(self, ch):
		self.set_output_param(ch, 0.0, 1.0)
		self.output_enable(1, True)
		
		# average over 10s
		t0 = time.time()
		accu = 0
		count = 0
		
		while True:
			q = self.query("MEAS:CURR?")
			q = str(q, encoding='ascii').strip().lower()
			if q == "nan":
				continue
			
			accu += float(q)
			count += 1
			
			if (time.time() - t0) > 10:
				break
		
		accu /= count
		self.ch_zeroes[ch] = accu
		
		print("Zero level: %.9f (%d samples)" % (accu, count))
		return accu
	
	def stop_logger(self):
		self.command_no_response("FLOG:STAT 0")
	
	def start_logger_file(self, log_duration=3600, srate='S500K'):
		self.command_no_response("FLOG:FILE:DUR %d" % log_duration)
		self.command_no_response("FLOG:SRAT %s" % srate)
		self.command_no_response("FLOG:STAT 1")
		
	def start_logger_scpi(self, srate='S500K', ch=1):
		self.command_no_response("FLOG:STAT 0")
		self.command_no_response("FLOG:FILE 0")
		self.command_no_response("FLOG:TARG SCPI")
		self.command_no_response("STAT:OPER:INST:ISUM%d:ENAB 4096") # Enable FastLogDataAvailable bit 12
		self.command_no_response("FLOG:SRAT %s" % srate)
		self.command_no_response("FLOG:STAT 1")
	
	def is_logger_running(self):
		return bool(int(self.query("FLOG:STAT?")))
	
	def get_logger_data_availability(self, ch):
		# read FastLogDataAvailable bit 12
		reg = int(self.query("STAT:OPER:INST:ISUM%d?" % ch))
		self.command_no_response("\n")
		return bool(reg & 4096)
	
	def read_logger_data(self):
		# Read first chunk.  Extract size and determine how much more needs to be read.
		first = self.query("FLOG:DATA?")
		output = b""
		
		check = first[0]
		digits = first[1] - ord('0')
		size = int(first[2:2+digits])
		
		# add first data
		output += first[2+digits:]
		size -= len(first[2+digits:])
		
		# read subsequent data until size == 0
		while size > 0:
			#print(size)
			block = self.continue_socket_recv()
			output += block
			size -= len(block)
			
		return output
	
	def zero_accumulators(self):
		self.ah_total = 0
		self.wh_total = 0
		self.nsamp = 0
	
	def process_ah_block(self, ch, raw_data, srate=500000):
		count = int(len(raw_data) / 8)  # 1 extra byte seems to be included (LF), ignore this
		sample_scale = (1e15 * (1.0 / srate)) / 3600
		
		v_sum = 0
		i_sum = 0
		w_sum = 0
		sub_samp = 0
		
		for n in range(count):
			v, i = self.fparser.unpack_from(raw_data, n * 8)
			i -= self.ch_zeroes[ch]
			w = v * i
			self.ah_total += int(int(int(i * 1e6) * sample_scale) / 1e6)
			self.wh_total += int(int(int(w * 1e6) * sample_scale) / 1e6)
			self.nsamp += 1
			v_sum += v
			i_sum += i
			w_sum += w
			sub_samp += 1
		
		v_avg = v_sum / sub_samp
		i_avg = i_sum / sub_samp
		w_avg = w_sum / sub_samp
		
		line = [self.ah_total / 1e15, self.wh_total / 1e15, v_avg, i_avg, w_avg, sub_samp, self.nsamp, sub_samp / (time.time() - self.tlast)]
		self.tlast = time.time()
		return line
	
		