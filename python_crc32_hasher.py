#!/usr/bin/python
# encoding: utf-8
# Copyright (C) 2013 Nguyen Hung Quy a.k.a dreamer2908
#
# Python CRC-32 Hasher is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import sys, os, zlib, hashlib, fnmatch, shutil, re, time, struct

programName = "Python CRC-32 Hasher"
version = "1.6"
author = "dreamer2908"

addcrc = False
force = False
recursive = False
searchSubFolder = False
createsfv = False
showChecksumResult = True
waitBeforeExit = False

sfvPath = "checksums.sfv"
sfvHeader = "; Generated by %s v%s " % (programName, version)
sfvContent = []
sfvPureAscii = True

enableMd5 = True
enableSha1 = True
enableSha224 = False
enableSha256 = False
enableSha384 = False
enableSha512 = False
enableEd2k = False

st_total = 0
st_ok = 0
st_notok = 0
st_error = 0
st_notfound = 0
st_size = 0

debug = False
fag = []
terminalSupportUnicode = False

# Open the file in binary mode (important) for reading. Get a unit of data,
# call zlib.crc32 to get its hash. Then get another unit, and call crc32 again;
# this time, also give it the hash just got from previous data.
# It will continue to calculate the hash. Repeat this until EOF.
# The hash got from calculating unit by unit is the same as the one got from
# processing everything in one blast. Memory consuming is lower this way.
# v2 uses a read cache instead of reading line by line.
# CPU usage is reduced by upto 40% (23s vs. 39s).
# According to my benchmark, without OS disk cache (or file much larger than the cache),
# 1 MiB of cache gives much higher speed than 100 KiB (59.247 MiB/s vs. 31.205 MiB/s),
# but consumes about 10% more CPU; 4 MiB of cache doesn't give any benefit over 1 MiB.
# With OS disk cache (files much smaller than the cache), speed: 100 KiB > 1 MiB > 4 MiB,
# CPU usage: 100 KiB < 1 MiB < 4 MiB. 1 MiB cache seems to be the best choice.
# All tests were done on Windows 7 SP1 x64 and Python 3.3.3 x86.
# Additional tests on Python 2.7.4, 3.3.1, PyPy3 2.1 Beta 1, PyPy 2.2.1 (Mint 15 x64):
# 4 MiB cache gives about 3-5% more speed than 1 MiB does (119.707 vs. 111.884 MiB/s)
# PyPy3, surprisingly, give bad results: it consumes the whole core, but runs much
# slower (56.497 MiB/s). PyPy gives less but still bad results (85.958 MiB/s)
# PyPy is usually faster than normal Python, but unfortunately, not with this program.
# Maybe some problems in their zlib implemention causes CPU botneck.
# Changed to 2 MiB cache. Slightly better on fast disks.
def crc32v2(fileName):
	fileSize = os.path.getsize(fileName)
	crc = 0
	md5 = hashlib.md5()
	sha1 = hashlib.sha1()
	sha224 = hashlib.sha224()
	sha256 = hashlib.sha256()
	sha384 = hashlib.sha384()
	sha512 = hashlib.sha512()
	ed2kBlockSize = 9728000
	ed2kBuf = bytearray()
	ed2kHash = bytearray()
	try:
		fd = open(fileName, 'rb')
		while True:
			buffer = fd.read(2 * 1024 * 1024)
			if len(buffer) == 0:
				fd.close()
				md4 = hashlib.new('md4')
				md4.update(ed2kBuf)
				ed2kHash += md4.digest()
				if fileSize >= ed2kBlockSize:
					md4 = hashlib.new('md4')
					md4.update(ed2kHash)
				ed2kHash = md4.hexdigest()
				return crc, md5.hexdigest().upper(), sha1.hexdigest().upper(), sha224.hexdigest().upper(), sha256.hexdigest().upper(), sha384.hexdigest().upper(), sha512.hexdigest().upper(), ed2kHash.upper(), False
			crc = zlib.crc32(buffer, crc)
			if enableMd5: md5.update(buffer)
			if enableSha1: sha1.update(buffer)
			if enableSha224: sha224.update(buffer)
			if enableSha256: sha256.update(buffer)
			if enableSha384: sha384.update(buffer)
			if enableSha512: sha512.update(buffer)

			if enableEd2k:
				ed2kBuf.extend(buffer)
				ed2kBufLen = len(ed2kBuf)
				while ed2kBufLen >= ed2kBlockSize:
					md4 = hashlib.new('md4')
					md4.update(ed2kBuf[0: ed2kBlockSize])
					ed2kHash += md4.digest()
					ed2kBuf = ed2kBuf[ed2kBlockSize:]
					ed2kBufLen = len(ed2kBuf)
	except Exception as e:
		if sys.version_info[0] < 3:
			error = unicode(e)
		else:
			error = str(e)
		return 0, '', '', '', '', '', '', '', error

# From version 2.6, the return value is in the range [-2**31, 2**31-1],
# and from ver 3.0, the return value is unsigned and in the range [0, 2**32-1]
# This works on both versions, confirmed by checking over 33 different files
def crc32_s(fileName):
	iHash, md5, sha1, sha224, sha256, sha384, sha512, ed2k, error = crc32v2(fileName)
	if sys.version_info[0] < 3 and iHash < 0:
		iHash += 2 ** 32
	sHash = '%08X' % iHash
	return sHash, md5, sha1, sha224, sha256, sha384, sha512, ed2k, error

# In-used CRC-32 pattern: 8 characters of hexadecimal,
# separated from the rest by some certain "special" characters.
# It's usually at the end of file name, so just take the last one;
# there shouldn't more than one anyway.
def detectCRC(fileName):
	crc = ""
	found = False
	reCRC = re.compile(r'[A-Fa-f0-9]{8}')
	separator1 = "([_. "
	separator2 = ")]_. "
	for match in reCRC.finditer(fileName):
		start = match.start()
		end = match.end()
		if ((start == 0 or fileName[start - 1] in separator1)
			and (end == len(fileName) or fileName[end + 1] in separator2)):
			crc = fileName[start:end]
			found = True
	return found, crc

def processFile(fileName):
	# Not gonna trust the caller completely
	if not os.path.isfile(fileName):
		fag.append(fileName)
		return

	# In Python 2, decode the path to unicode string
	# In python 3, it's already unicode, so don't
	if sys.version_info[0] < 3 and hasattr(fileName, 'decode'):
		fileName = fileName.decode(sys.getfilesystemencoding())

	sHash, md5, sha1, sha224, sha256, sha384, sha512, ed2k, error = crc32_s(fileName)
	newName = fileName

	global st_total, st_ok, st_notok, st_notfound, st_size, st_error
	if not error:
		try:
			st_size += os.path.getsize(fileName)
		except:
			doNothing = 1
	st_total += 1

	found, crc = detectCRC(fileName)

	if error:
		result = error
		st_error += 1
	elif sHash in fileName.upper():
		result = "File OK!"
		st_ok += 1
	elif found:
		result = "File not OK! %s found in filename." % crc
		st_notok += 1
	else:
		if addcrc:
			namae, ext = os.path.splitext(fileName)
			newName = namae + "[%s]" % sHash + ext
			try:
				shutil.move(fileName, newName)
				result = "CRC added!"
			except:
				result = "Renaming failed!"
				newName = fileName
		else:
			result = "CRC not found!"
		st_notfound += 1

	# deal with terminal encoding mess
	global terminalSupportUnicode
	if not terminalSupportUnicode:
		fileName = removeNonAscii(fileName)

	if showChecksumResult:
		print('%s    %s    %s' % (fileName, sHash, result))
		if not error:
			if enableMd5: print('MD5: %s' % md5)
			if enableSha1: print('SHA-1: %s' % sha1)
			if enableSha224: print('SHA-224: %s' % sha224)
			if enableSha256: print('SHA-256: %s' % sha256)
			if enableSha384: print('SHA-384: %s' % sha384)
			if enableSha512: print('SHA-512: %s' % sha512)
			if enableEd2k: print('ED2K: %s' % ed2k)

	# Append this file info to sfvContent. Yes, use newName as it's up-to-date
	# Use "global" to access external variable (important)
	path, name = os.path.split(newName)
	if not error:
		global sfvContent
		sfvContent.append('\n')
		sfvContent.append(name)
		sfvContent.append(' ')
		sfvContent.append(sHash)

		global sfvPureAscii
		if sfvPureAscii:
			sfvPureAscii = isPureAscii(name)

def processFolderv2(path):

	pattern = '*'
	usePattern = False

	# Check if the input is an existing folder.
	# If not, split the path and check if "folder" exists
	if not os.path.isdir(path):
		folder, pattern = os.path.split(path)
		if os.path.isdir(folder):
			path = folder
			usePattern = True
		elif folder == '':
			path = os.getcwd()
			usePattern = True
		else:
			return

	for (dirpath, dirnames, filenames) in os.walk(path):
		if usePattern:
			filenames = fnmatch.filter(filenames, pattern)
		for fname in filenames:
			processFile(os.path.join(dirpath, fname))
		if (not usePattern and not recursive) or (usePattern and not searchSubFolder):
			break

# Calculate CPU time and average CPU usage
def getCpuStat(cpuOld, cpuNew, timeOld, timeNew):
	cpuTime = float(cpuNew) - float(cpuOld)
	elapsedTime = float(timeNew) - float(timeOld)

	if cpuTime == 0:
		cpuTime = 0.001
		elapsedTime = cpuTime
	if elapsedTime == 0:
		elapsedTime = cpuTime

	cpuPercentage = 100 * cpuTime / elapsedTime

	# Devide CPU percentage by the number of CPUs if it's Windows
	# to match reference system monitors (Windows Task Manager, etc.)
	if sys.platform == 'win32':
		cpuPercentage = cpuPercentage / detectCPUs()

	return cpuTime, cpuPercentage, elapsedTime

# Detects the number of CPUs on a system. Cribbed from pp + some modifications
# Alternative:  multiprocessing.cpu_count()
def detectCPUs():
	# Linux, Unix and MacOS:
	if hasattr(os, "sysconf"):
		if os.sysconf_names.has_key("SC_NPROCESSORS_ONLN"):
			# Linux & Unix:
			ncpus = os.sysconf("SC_NPROCESSORS_ONLN")
			if isinstance(ncpus, int) and ncpus > 0:
				return ncpus
		else: # OSX:
			return int(os.popen2("sysctl -n hw.ncpu")[1].read())
	# Windows:
	if sys.platform == 'win32':
		ncpus = int(os.getenv("NUMBER_OF_PROCESSORS", 0));
		if ncpus > 0:
			return ncpus
	return 1 # Default


# Test unicode support
def terminalSupportUnicodeed():
	try:
		text = u'「いなり、こんこん、恋いろは。」番宣ＰＶ'.encode(sys.stdout.encoding)
	except:
		return False
	return True

def isPureAscii(text):
	for c in text:
		code = ord(c)
		if code > 127:
			return False
	return True

# Converts text into UTF-16LE bytes
# Yes, re-inverted the wheel
def toUTF16leBytes(text):
	encodedBytes = bytearray()
	for c in text:
		encodedBytes += toUTF16leBytesSub(c)
	return encodedBytes

# Encodes a single character
# See RFC 2781, UTF-16, an encoding of ISO 10646 http://www.ietf.org/rfc/rfc2781.txt
# Reference encoder: Unicode Code Converter http://rishida.net/tools/conversion/
def toUTF16leBytesSub(c):
	U = ord(c)
	if U < 0x10000:
		return struct.pack("<H", U)
	else:
		U = U - 0x10000
		W1 = 0xD800
		W2 = 0xDC00
		UH = U >> 10
		UL = U - (UH << 10)
		W1 ^= UH
		W2 ^= UL
		return struct.pack('<HH', W1, W2)

def toAsciiBytes(text):
	return removeNonAscii(text).encode('ascii')

# Kills non-ASCII characters
def removeNonAscii(original):
	result = ''
	for c in original:
		code = ord(c)
		if code < 128:
			result += c
		else:
			result += '?'
	return result

# Parse paramenters
pathList = []
i = 1
while i < len(sys.argv):
	arg = sys.argv[i]
	if arg == "--addcrc" or arg == "-addcrc":
		addcrc = True
	elif (arg == "--createsfv" or arg == "-createsfv") and i < len(sys.argv) - 1:
		createsfv = True
		sfvPath = sys.argv[i+1]
		i += 1
	elif arg == "--f" or arg == "-f":
		force == True
	elif arg == "--r" or arg == "-r":
		recursive = True
	elif arg == "--s" or arg == "-s":
		searchSubFolder = True
	elif arg == "--ncr" or arg == "-ncr":
		showChecksumResult = False
	elif arg == "--md5" or arg == "-md5":
		enableMd5 = True
	elif arg == "--sha1" or arg == "-sha1":
		enableSha1 = True
	elif arg == "--sha224" or arg == "-sha224":
		enableSha224 = True
	elif arg == "--sha256" or arg == "-sha256":
		enableSha256 = True
	elif arg == "--sha384" or arg == "-sha384":
		enableSha384 = True
	elif arg == "--sha512" or arg == "-sha512":
		enableSha512 = True
	elif arg == "--ed2k" or arg == "-ed2k":
		enableEd2k = True
	elif arg == "--d" or arg == '--debug' or arg == '-debug' or arg == '-d':
		debug = True
	elif arg == "--w" or arg == "-w":
		waitBeforeExit = True
	elif arg == "--all" or arg == "-all":
		enableMd5 = True
		enableSha1 = True
		enableSha224 = True
		enableSha256 = True
		enableSha384 = True
		enableSha512 = True
		enableEd2k = True
	else:
		pathList.append(arg)
	i += 1

# Print user manual
if len(pathList) < 1:
	print("%s v%s by %s\n" % (programName, version, author))
	print("Syntax: python crc32.py [options] inputs\n")
	print("Input can be individual files, and/or folders.")
	print("  Use Unix shell-style wildcard (*, ?) for the filename pattern.\n")
	print("Options:")
	print("  --addcrc                        Add CRC-32 to filenames.")
	print("  --createsfv out.sfv             Create a SFV file.")
	print("  --r                             Also include sub-folder.")
	print("  --s                             Also search sub-folder for matching filenames.")
	print("  --md5                           Calculate MD5 hash.")
	print("  --sha1                          Calculate SHA1 hash.")
	print("  --sha*                          Calculate SHA2-224/256/384/512 hashes.")
	print("  --ed2k                          Calculate ED2K hash.")
	print("  --all                           Calculate all supported hashes.")
	print("  CRC-32 calculation is enabled by default.\n")
	print("Examples:")
	print('  python crc32.py \"/home/yumi/Desktop/[FFF] Unbreakable Machine-Doll - 11 [A3A1001B].mkv\"')
	print('  python crc32.py --md5 ~/Desktop ~/Downloads/*.mkv \"/var/www/upload/Ep ??.mkv\"')
	print('  python crc32.py --sha512 --createsfv checksums.sfv --s --addcrc /var/www/upload/*.mp4 ')
	sys.exit()

# Stats setup
if sys.platform == 'win32':
    # On Windows, the best timer is time.clock
    default_timer = time.clock
else:
    # On most other platforms the best timer is time.time
    default_timer = time.time

startTime = default_timer()
uOld, sOld, cOld, c, e = os.times()

sfvContent.append(sfvHeader)
sfvPureAscii = True
terminalSupportUnicode = terminalSupportUnicodeed()

# Process files and folders
print('')
if debug:
	print(pathList)

for path in pathList:
	if os.path.isfile(path):
		processFile(path) # processFolderv2 also works with file, but this saves some cpu circles
	elif os.path.isdir(path):
		processFolderv2(path)
	elif (path.endswith(os.sep) or path.endswith("'") or path.endswith('"')) and os.path.isdir(path[:-1]):
		processFolderv2(path[:-1])
	elif ("*" in path) or ("?" in path): # depreciated
	 	processFolderv2(path)
	else:
		processFolderv2(path)

endTime = default_timer()

if createsfv:
	try:
		sfvFile = open(sfvPath, 'wb')
		# encode to UTF-16LE if there is any non-ascii character
		if sfvPureAscii:
			for content in sfvContent:
				sfvFile.write(toAsciiBytes(content))
		else:
			# write BOM
			sfvFile.write(struct.pack("<B", 255))
			sfvFile.write(struct.pack("<B", 254))
			for content in sfvContent:
				sfvFile.write(toUTF16leBytes(content))
		sfvFile.close()
	except:
		print("Couldn't open \"%s\" for writing!" % sfvPath)

# Print stats

uNew, sNew, cNew, c, e = os.times()
cpuTime, cpuPercentage, elapsed = getCpuStat(uOld + sOld, uNew + sNew, startTime, endTime)

print("\nTotal: %d. OK: %d. Not OK: %d. CRC not found: %d. Error: %d." % (st_total, st_ok, st_notok, st_notfound, st_error))

speed = st_size * 1.0 / elapsed
if speed >= 1000 * 1024 * 1024:
	print("Speed: %0.3f GiB read in %0.3f sec => %0.3f GiB/s." % (st_size / (1024 * 1024 * 1024), elapsed, speed / (1024 * 1024 * 1024)))
elif speed >= 1000 * 1024:
	print("Speed: %0.3f MiB read in %0.3f sec => %0.3f MiB/s." % (st_size / (1024 * 1024), elapsed, speed / (1024 * 1024)))
elif speed >= 1000:
	print("Speed: %0.3f KiB read in %0.3f sec => %0.3f KiB/s." % (st_size / (1024), elapsed, speed / (1024)))
else:
	print("Speed: %0.3f B read in %0.3f sec =>  %0.0f B/s." % (st_size, elapsed, speed))

print('CPU time: %0.3f sec => Average: %0.2f %%.' % (cpuTime, cpuPercentage))

# So many bugs
if debug:
	print(' ')
	print('Terminal supporting unicode = %s' % terminalSupportUnicodeed())
	print('fag = %r' % fag)

if waitBeforeExit:
	print(' ')
	if sys.version_info[0] < 3:
		dummy = raw_input('Press Enter To Exit...')
	else:
		dummy = input('Press Enter To Exit...')