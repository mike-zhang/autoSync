#!/usr/bin/env python
#-*- coding:utf-8 -*-

import time,os,sys
import paramiko
import posixpath, traceback
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigData():        
    def __init__(self,_fileName):
        self.fileName = _fileName
        self.docTree = None

        self.ssh_host = "127.0.0.1"
        self.ssh_port = 22
        self.ssh_user = "root"
        self.ssh_passwd = ""
        self.currentDir = "."
        self.remoteDir = "/tmp/t1"        
        
        self.arrFileExcept = []
        self.getConfigFromFile()
        
    def show(self):
        print self.ssh_host
        print self.ssh_port
        print self.ssh_user
        print self.ssh_passwd
        print self.currentDir
        print self.remoteDir
        print self.arrFileExcept
 
    def getSectiontText(self,path):
        retText = ""
        if self.docTree :
            objTmp = self.docTree.find(path)
            if objTmp != None : 
                retText = objTmp.text or ""                
        return retText

    def getFileExcept(self):        
        if not self.docTree : 
            return None            
        objTmp = self.docTree.findall("fileExcept/file")            
        if objTmp :
            self.arrFileExcept += [os.path.join(self.currentDir,item.text) for item in objTmp]            
        return None
        
    def getSectiontInt(self,path):    
        strTmp = self.getSectiontText(path).strip()
        return (int(strTmp) if strTmp.isdigit() else 0)    
    
    def getConfigFromFile(self):        
        try:
            import xml.etree.cElementTree as ET
        except ImportError:
            import xml.etree.ElementTree as ET    
        if not os.path.exists(self.fileName) : 
            print "file ", self.fileName, " not exists"
            return None        
        try:
            self.docTree = ET.ElementTree(file=self.fileName)            
        except Exception,e:
            print "%s is NOT well-formed : %s "%(self.fileName,e)
            return None
        
        self.ssh_host = self.getSectiontText("host").strip()
        self.ssh_port = self.getSectiontInt("sshPort")
        self.ssh_user = self.getSectiontText("user").strip()
        self.ssh_passwd = self.getSectiontText("password").strip()        
        self.currentDir = self.getSectiontText("localDir").strip()
        self.currentDir = os.path.abspath(self.currentDir)    
        self.remoteDir = self.getSectiontText("remoteDir").strip()        
        self.getFileExcept()
        return None


def getSSHInstance(cnf):
    ssh=paramiko.SSHClient() 
    #ssh.load_system_host_keys() 
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=cnf.ssh_host,
                port=cnf.ssh_port,
                username=cnf.ssh_user,
                password=cnf.ssh_passwd,
                timeout=5)     
    return ssh
    
def doScp(srcPath,cnf):
    bRet = False    
    try:
        print "srcPath : {0}".format(srcPath)
        if srcPath in cnf.arrFileExcept :
            print "{0} in arrFilesExcept".format(srcPath)
            return bRet        
        srcFile = os.path.relpath(srcPath,cnf.currentDir)
        dstFile = posixpath.join(cnf.remoteDir,srcFile.replace(os.path.sep, posixpath.sep))
        print dstFile        
        print("doScp : {0},{1}".format(srcPath,dstFile))
        if not os.path.exists(srcPath) :
            print("doScp : file {0} not exist".format(srcPath))
            bRet = False            
        else :
            ssh = getSSHInstance(cnf)
            strcmd = "mkdir -p {0}".format(posixpath.split(dstFile)[0])
            print strcmd
            stdin,stdout,stderr=ssh.exec_command(strcmd)
            sftp = paramiko.SFTPClient.from_transport(ssh.get_transport())
            sftp = ssh.open_sftp()
            sftp.put(srcPath,dstFile)
            ssh.close()
            bRet = True
    except :
        print "error occur"        
        print traceback.format_exc()
        bRet = False
    return bRet      

def doRemoteCmd(cnf,strcmd):
    bRet = False    
    try:        
        ssh = getSSHInstance(cnf)        
        print strcmd
        stdin,stdout,stderr=ssh.exec_command(strcmd)        
        bRet = True
    except :        
        print traceback.format_exc()
        bRet = False
    return bRet 

class SyncHandler(FileSystemEventHandler):
    def __init__(self, conf):
        self.conf = conf
        
    def doFileSync(self,event):
        if not event.is_directory : 
            srcFile = event.src_path
            srcFile = os.path.abspath(srcFile)
            doScp(srcFile,self.conf)
        return None
    
    def doFileDelete(self, event):
        if not event.is_directory :             
            srcPath = os.path.abspath(event.src_path)        
            srcFile = os.path.relpath(srcPath,self.conf.currentDir)
            dstFile = posixpath.join(self.conf.remoteDir,srcFile.replace(os.path.sep, posixpath.sep))
            print dstFile
            if dstFile :
                strcmd = "rm -f {0}".format(dstFile)
                doRemoteCmd(self.conf, strcmd)
        return None        
        
    def on_modified(self, event):
        print event.key    
        self.doFileSync(event)
        
    def on_deleted(self, event):
        print event.key
        self.doFileDelete(event)
    
    def on_moved(self,event):
        print event.key,"moved"
        self.doFileDelete(event)
        self.doFileSync(event)        
  
if __name__ == "__main__":    
    if len(sys.argv) < 2 :
        print "usage : %s conf.xml" % sys.argv[0]
        sys.exit(1)
    confFile = sys.argv[1]
        
    conf = ConfigData(confFile)
    conf.show()
    
    print conf.arrFileExcept
    
    # do sync in start
    for root, dirs, files in os.walk(conf.currentDir):
        for name in files:            
            t_path = os.path.join(root, name)
            t_path = os.path.abspath(t_path)
            print t_path, name
            doScp(t_path,conf)
    # do sync on modify
    event_handler = SyncHandler(conf)
    observer = Observer()
    observer.schedule(event_handler, path=conf.currentDir, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    