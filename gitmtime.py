#!/usr/bin/python
import os
import os.path
import subprocess
import sys, getopt
import json
import datetime
import re
from datetime import datetime
import time
import calendar
import logging
import hashlib

VerboseFlag = False
ConfigFile = "gitmtime.cfg"
ConfigData = {}
BUF_SIZE = 65536  # lets read stuff in 64kb chunks!

#------------------------------------------------------------------------------
# Common Functions
#------------------------------------------------------------------------------
def IsLinux():
  if os.name == 'nt':
    st = False
  else:
    st = True
  return st

def Exec(cmd):
  global VerboseFlag
  if VerboseFlag:
    print "Exec: %s" % (cmd)
  p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  out, err = p.communicate()
  status = p.wait()
  if VerboseFlag:
    print out
    print "Status=%d, our=[%s], err=[%s]" % (status, out, err)
  if out == "":
    out = err  
  return status, out

def WriteDataToFile(fn, text):
  fp = open(fn, "w")
  fp.write(text)
  fp.close()

def ReadDataFromFile(fn):
  fp = open(fn, 'r')
  data = fp.read()
  fp.close()
  return data

def DeleteFile(fn):
  if os.path.isfile(fn):
    os.remove(fn)

def MakeFolder(folder):
  if not os.path.exists(folder):
    os.makedirs(folder)

def MoveFile(src, dest):
  dir = os.path.dirname (dest)
  MakeFolder(dir)
  os.rename(src, dest)

def json_encode(data):
  return json.dumps(data)

def json_decode(data):
  return json.loads(data)

def isset(variable):
  st = True
  try:
    variable
  except NameError:
    st = False
  return st

def ReadFileToArray(fn):
  with open(fn) as f:
    lines = f.readlines()
    f.close()
  return lines

def WriteArrayToFile(fn, lines):
  fo = open(fn, "w")
  line = fo.writelines(lines)
  fo.close()

def GetFileExtension(fn):  
  return os.path.splitext(fn)[1]

def GetFileSha1 (fn):
  sha1 = hashlib.sha1()
  with open(fn, 'rb') as f:
    while True:
      data = f.read(BUF_SIZE)
      if not data:
          break
      sha1.update(data)
  return sha1.hexdigest()

#------------------------------------------------------------------------------
# GIT Functions
#------------------------------------------------------------------------------
class GitFolderClass:
  Folder = "."
  ValidFlag = False
  FileDatabase = {}
  
  def __init__(self, folder = "."):
    self.Folder = folder
    self.ValidFlag = self.IsValid()
    
  def IsValid(self):
    st = False
    status, result = Exec("git status %s" % (self.Folder))
    if status == 0:
      if "Not a git repository" not in result:
        st = True
    return st
    
  def GetMTimeFromFile(self, fn):
    return os.path.getmtime(fn)

  def GetFInfoFromDatabase(self, fn):
    finfo = False
    if fn in self.FileDatabase:
      finfo = self.FileDatabase[fn]
    return finfo
    
  def GetMTimeFromGit(self, fn):
    mtime = False
    status, iso_time = Exec("git log --pretty=format:%%cd -n 1 --format=%%ai -- %s" % (fn))
    if status == 0 and iso_time != "":
      iso_time = iso_time.strip();        # "2017-08-10 12:54:58 +0800" => "2017-08-10 12:54:58"
      iso_time = iso_time[:-5].strip()
      ftime = datetime.strptime(iso_time, "%Y-%m-%d %H:%M:%S")
      mtime = calendar.timegm(ftime.timetuple())
    return mtime
    
  def UpdateFileMTime(self, fn, mtime):
    os.utime (fn, (mtime, mtime))
    iso_time = datetime.fromtimestamp(int(mtime)).strftime('%Y-%m-%d %H:%M:%S')
    if VerboseFlag:
      print "Info: Update mtime of [%s] to [%s]" % (fn, iso_time)
    logging.info('Update mtime of [%s] to [%s]' % (fn, iso_time))
        
  def UpdateMTime(self, qflag):
    status, result = Exec("git ls-files")
    if status == 0:
      lines = result.split("\n")
      for line in lines:
        fn = line.strip()
        if not fn: 
          continue
        if os.path.isfile(fn) == False:
          print "Error: file not found [%s]" % (fn)
          continue
        finfo = self.GetFInfoFromDatabase(fn) 
        if finfo == False:                      # No record in database
          if qflag:
            mtime = self.GetMTimeFromFile (fn)     # Get mtime from File (Quick Mode)
          else:
            mtime = self.GetMTimeFromGit (fn)     # Get mtime from GIT
          if mtime != False:
            self.UpdateFileMTime (fn, mtime)
            finfo = {}
            finfo['mtime'] = mtime
            finfo['size'] = os.stat(fn).st_size  
            finfo['sha1'] = GetFileSha1(fn)
            self.FileDatabase[fn] = finfo
        else:                                   # had record
          mtime = self.GetMTimeFromFile(fn)
          if finfo['mtime'] != mtime:           # but time diff
            sha1 = GetFileSha1(fn)
            if sha1 == finfo['sha1']:           # sha1 is same, update mtime to file
              self.UpdateFileMTime (fn, finfo['mtime'])
            else:                               # sha1 is diff, get mtime from GIT
              mtime = self.GetMTimeFromGit (fn)
              if mtime != False:
                finfo = {}
                finfo['mtime'] = mtime
                finfo['size'] = os.stat(fn).st_size  
                finfo['sha1'] = sha1
                self.FileDatabase[fn] = finfo
          
#------------------------------------------------------------------------------
# Config Functions
#------------------------------------------------------------------------------
def LoadConfig():
  global ConfigFile
  global ConfigData
  if os.path.isfile(ConfigFile):
    jdata = ReadDataFromFile(ConfigFile)
    try:
      ConfigData = json_decode(jdata)
    except:
      ConfigData = {}    
    
def SaveConfig():
  global ConfigFile
  global ConfigData
  jdata = json_encode(ConfigData)
  WriteDataToFile(ConfigFile, jdata)

#------------------------------------------------------------------------------
# Main
#------------------------------------------------------------------------------
def Usage():
    print 'Python gitmtime.py -y -t -v -s'
    print '   -u        Update database and mtime of all files'
    print '   -c        Empty database for rebuild'
    print '   -q        Quick mode, Use Local File System for rebuild'
    print '   -t        Test'
    print '   -v        Verbose'

def main(argv):
  global VerboseFlag
  global ConfigData
  
  TestFlag = False
  SpaceFlag = False
  UpdateFlag = False
  ClearMTimeFlag = False
  QuickFlag = False
  
  logging.basicConfig(filename='gitmtime.log', level=logging.INFO)
    
  try:
    opts, args = getopt.getopt(argv,"ucqvh",["help"])
  except getopt.GetoptError:
    Usage()
    sys.exit(2)
  for opt, arg in opts:
    if opt == '-h':
      Usage()
      sys.exit()
    elif opt == "-u":                 # Update mtime database
      UpdateFlag = True
    elif opt == "-c":                 # Clear modified time database
      ClearMTimeFlag = True
    elif opt == "-q":                 # Quick Flag for rebuild
      QuickFlag = True
    elif opt == "-v":                 # Verbose Flag
      VerboseFlag = True
  
  if TestFlag != False:
    sys.exit()

  sobj = GitFolderClass()
  if sobj.ValidFlag == False:
    print "Error: not a GIT working copy"
    sys.exit(2)

  LoadConfig()

  print "QuickFlag = %d" % (QuickFlag)
  
  if UpdateFlag:
    sobj = GitFolderClass()
    if ClearMTimeFlag == False and "FDB" in ConfigData:
      sobj.FileDatabase = ConfigData['FDB']
    sobj.UpdateMTime (QuickFlag)
    ConfigData['FDB'] = sobj.FileDatabase
  
  SaveConfig()
    
if __name__ == "__main__":
   main(sys.argv[1:])
