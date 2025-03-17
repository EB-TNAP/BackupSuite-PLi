# -*- coding: utf-8 -*-
from .schermen import *
import os
import gettext
from functools import lru_cache
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Console import Console
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.FileList import FileList
from Components.Language import language
from Components.Harddisk import harddiskmanager
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Plugins.Plugin import PluginDescriptor
from Tools.Directories import resolveFilename, SCOPE_LANGUAGE, SCOPE_PLUGINS
from os import environ
from enigma import getDesktop

# Optimize box type import with fallback
try:
    from enigma import getBoxType
except ImportError:
    from boxbranding import getBoxType

# Setup language
lang = language.getLanguage()
environ["LANGUAGE"] = lang[:2]
gettext.bindtextdomain("enigma2", resolveFilename(SCOPE_LANGUAGE))
gettext.textdomain("enigma2")
gettext.bindtextdomain("BackupSuite", "%s%s" % (resolveFilename(SCOPE_PLUGINS), "Extensions/BackupSuite/locale"))

def _(txt):
    """Translate function with fallback"""
    t = gettext.dgettext("BackupSuite", txt)
    if t == txt:
        t = gettext.gettext(txt)
    return t

# -------- Configuration and Global Variables --------

# Cache mounted partitions to avoid multiple scans
@lru_cache(maxsize=1)
def get_mount_choices():
    choices = [('none', 'None'), ("/media/net", _("NAS"))]
    for p in harddiskmanager.getMountedPartitions():
        d = os.path.normpath(p.mountpoint)
        if os.path.exists(p.mountpoint) and p.mountpoint != '/':
            choices.append((d, p.mountpoint))
    return choices

# Get mount choices for config
wherechoises = get_mount_choices()

# Global variables
autoStartTimer = None
_session = None

# -------- Constants --------

# Paths to backup scripts
BACKUP_HDD = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite/backuphdd.sh")
BACKUP_USB = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite/backupusb.sh")
BACKUP_MMC = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite/backupmmc.sh")
BACKUP_DMM_HDD = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite/backuphdd-dmm.sh")
BACKUP_DMM_USB = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite/backupusb-dmm.sh")
BACKUP_DMM_MMC = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite/backupmmc-dmm.sh")

# Other constants
ofgwrite_bin = "/usr/bin/ofgwrite"
LOGFILE = "BackupSuite.log"
VERSIONFILE = "imageversion"
ENIGMA2VERSIONFILE = "/tmp/enigma2version"

# Get version number from control file
try:
    with open("/var/lib/opkg/info/enigma2-plugin-extensions-backupsuite.control") as origin:
        for versie in origin:
            if "Version: " in versie:
                try:
                    versienummer = versie.split('+')[1].strip()
                    break
                except IndexError:
                    versienummer = "unknown"
                    print("[BackupSuite] can't detect version!")
except (IOError, OSError):
    versienummer = "unknown"
    print("[BackupSuite] can't find control file!")

# -------- Helper Functions --------

def backupCommandHDD():
    """Return the appropriate backup command for HDD based on box type"""
    if getBoxType().startswith("dm"):
        cmd = BACKUP_DMM_HDD + ' en_EN'
    else:
        cmd = BACKUP_HDD + ' en_EN'
    return cmd

def backupCommandUSB():
    """Return the appropriate backup command for USB based on box type"""
    if getBoxType().startswith("dm"):
        cmd = BACKUP_DMM_USB + ' en_EN'
    else:
        cmd = BACKUP_USB + ' en_EN'
    return cmd

def backupCommandMMC():
    """Return the appropriate backup command for MMC based on box type"""
    if getBoxType().startswith("dm"):
        cmd = BACKUP_DMM_MMC + ' en_EN'
    else:
        cmd = BACKUP_MMC + ' en_EN'
    return cmd

# -------- Help System Integration --------

try:
    from Plugins.SystemPlugins.MPHelp import registerHelp, XMLHelpReader
    reader = XMLHelpReader(resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite/mphelp.xml"))
    backupsuiteHelp = registerHelp(*reader)
except Exception as e:
    print("[BackupSuite] Unable to initialize MPHelp:", e, "- Help not available!")
    backupsuiteHelp = None

# -------- Main Screens --------

class BackupStart(Screen):
    """Main screen for backup operations"""
    
    def __init__(self, session, args=0):
        # Select appropriate skin based on screen resolution
        try:
            sz_w = getDesktop(0).size().width()
        except:
            sz_w = 720
            
        if sz_w == 1920:
            self.skin = skinstartfullhd
        elif sz_w >= 1280:
            self.skin = skinstarthd
        else:
            self.skin = skinstartsd
            
        self.session = session
        self.setup_title = _("Make a backup or restore a backup")
        Screen.__init__(self, session)
        self.skin_path = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite")
        
        # Setup buttons
        self["key_menu"] = Button(_("Backup > MMC"))
        self["key_red"] = Button(_("Close"))
        self["key_green"] = Button(_("Backup > HDD"))
        self["key_yellow"] = Button(_("Backup > USB"))
        self["key_blue"] = Button(_("Restore backup"))
        self["help"] = StaticText()
        
        # Setup action map
        self["setupActions"] = ActionMap(["SetupActions", "ColorActions", "EPGSelectActions", "HelpActions"],
        {
            "menu": self.confirmmmc,
            "red": self.cancel,
            "green": self.confirmhdd,
            "yellow": self.confirmusb,
            "blue": self.flashimage,
            "info": self.keyInfo,
            "cancel": self.cancel,
            "displayHelp": self.showHelp,
        }, -2)
        
        self.setTitle(self.setup_title)

    def confirmhdd(self):
        """Confirm HDD backup operation"""
        self.session.openWithCallback(
            self.backuphdd, 
            MessageBox, 
            _("Do you want to make an USB-back-up image on HDD? \n\nThis only takes a few minutes and is fully automatic.\n"), 
            MessageBox.TYPE_YESNO, 
            timeout=20, 
            default=True
        )

    def confirmusb(self):
        """Confirm USB backup operation"""
        self.session.openWithCallback(
            self.backupusb, 
            MessageBox, 
            _("Do you want to make a back-up on USB?\n\nThis only takes a few minutes depending on the used filesystem and is fully automatic.\n\nMake sure you first insert an USB flash drive before you select Yes."), 
            MessageBox.TYPE_YESNO, 
            timeout=20, 
            default=True
        )

    def confirmmmc(self):
        """Confirm MMC backup operation"""
        self.session.openWithCallback(
            self.backupmmc, 
            MessageBox, 
            _("Do you want to make an USB-back-up image on MMC? \n\nThis only takes a few minutes and is fully automatic.\n"), 
            MessageBox.TYPE_YESNO, 
            timeout=20, 
            default=True
        )

    def showHelp(self):
        """Show help screen"""
        if backupsuiteHelp:
            backupsuiteHelp.open(self.session)

    def flashimage(self):
        """Open flash image screen"""
        model = getBoxType()
        
        # Determine file types based on box model
        if model in ("vuduo", "vusolo", "vuultimo", "vuuno") or model.startswith("ebox"):
            files = "^.*\.(zip|bin|jffs2)"
        elif "4k" in model or "uhd" in model or model in ("hd51", "hd60", "hd61", "h7", "sf4008", "sf5008", "sf8008", "sf8008m", "vs1500", "et11000", "et13000", "multibox", "multiboxplus", "e4hdultra"):
            files = "^.*\.(zip|bin|bz2)"
        elif model in ("h9", "h9se", "h9combo", "h9combose", "i55plus", "i55se", "h10", "hzero", "h8", "dinobotu55", "iziboxx3", "dinoboth265", "axashistwin", "protek4kx1"):
            files = "^.*\.(zip|bin|ubi)"
        elif model.startswith("dm"):
            self.session.open(MessageBox, _("No supported receiver found!"), MessageBox.TYPE_ERROR)
            return
        else:
            files = "^.*\.(zip|bin)"
            
        curdir = '/media/'
        self.session.open(FlashImageConfig, curdir, files)

    def cancel(self):
        """Close screen"""
        self.close(False, self.session)

    def keyInfo(self):
        """Show what's new info"""
        self.session.open(WhatisNewInfo)

    def writeEnigma2VersionFile(self):
        """Write current Enigma2 version to file"""
        from Components.About import getEnigmaVersionString
        with open(ENIGMA2VERSIONFILE, 'wt') as f:
            f.write(getEnigmaVersionString())

    def backuphdd(self, ret=False):
        """Start HDD backup if confirmed"""
        if ret:
            self.writeEnigma2VersionFile()
            text = _('Full back-up on HDD')
            cmd = backupCommandHDD()
            self.session.openWithCallback(self.consoleClosed, Console, text, [cmd])

    def backupusb(self, ret=False):
        """Start USB backup if confirmed"""
        if ret:
            self.writeEnigma2VersionFile()
            text = _('Full back-up to USB')
            cmd = backupCommandUSB()
            self.session.openWithCallback(self.consoleClosed, Console, text, [cmd])

    def backupmmc(self, ret=False):
        """Start MMC backup if confirmed"""
        if ret:
            self.writeEnigma2VersionFile()
            text = _('Full back-up on MMC')
            cmd = backupCommandMMC()
            self.session.openWithCallback(self.consoleClosed, Console, text, [cmd])

    def consoleClosed(self, answer=None):
        """Callback when console is closed"""
        return

# -------- Info Screen --------

class WhatisNewInfo(Screen):
    """Screen to display what's new information"""
    
    def __init__(self, session):
        # Select appropriate skin based on screen resolution
        try:
            sz_w = getDesktop(0).size().width()
        except:
            sz_w = 720
            
        if sz_w == 1920:
            self.skin = skinnewfullhd
        elif sz_w >= 1280:
            self.skin = skinnewhd
        else:
            self.skin = skinnewsd
            
        Screen.__init__(self, session)
        self.skin_path = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite")
        
        self["Title"].setText(_("What is new since the last release?"))
        self["key_red"] = Button(_("Close"))
        self["AboutScrollLabel"] = ScrollLabel(_("Please wait"))
        
        self["actions"] = ActionMap(["SetupActions", "DirectionActions"],
            {
                "cancel": self.close,
                "ok": self.close,
                "up": self["AboutScrollLabel"].pageUp,
                "down": self["AboutScrollLabel"].pageDown
            })
            
        # Load and display the whatsnew content
        whatsnew_path = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite/whatsnew.txt")
        try:
            with open(whatsnew_path) as file:
                whatsnew = file.read()
            self["AboutScrollLabel"].setText(whatsnew)
        except (IOError, OSError):
            self["AboutScrollLabel"].setText(_("Unable to load what's new information."))

# -------- Flash Image Screen --------

class FlashImageConfig(Screen):
    """Screen to configure and execute flashing of images"""
    
    def __init__(self, session, curdir, matchingPattern=None):
        # Select appropriate skin based on screen resolution
        try:
            sz_w = getDesktop(0).size().width()
        except:
            sz_w = 720
            
        if sz_w == 1920:
            self.skin = skinflashfullhd
        elif sz_w >= 1280:
            self.skin = skinflashhd
        else:
            self.skin = skinflashsd
            
        Screen.__init__(self, session)
        self.skin_path = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite")
        
        self["Title"].setText(_("Select the folder with backup"))
        self["key_red"] = StaticText(_("Close"))
        self["key_green"] = StaticText("")
        self["key_yellow"] = StaticText("")
        self["key_blue"] = StaticText("")
        self["curdir"] = StaticText(_("current:  %s") % (curdir or ''))
        
        self.founds = False
        self.dualboot = self.dualBoot()
        self.ForceMode = self.ForceMode()
        
        # Setup file browser
        self.filelist = FileList(curdir, matchingPattern=matchingPattern, enableWrapAround=True)
        self.filelist.onSelectionChanged.append(self.__selChanged)
        self["filelist"] = self.filelist
        
        self["FilelistActions"] = ActionMap(["SetupActions", "ColorActions"],
            {
                "green": self.keyGreen,
                "red": self.keyRed,
                "yellow": self.keyYellow,
                "blue": self.KeyBlue,
                "ok": self.keyOk,
                "cancel": self.keyRed
            })
            
        self.onLayoutFinish.append(self.__layoutFinished)

    def __layoutFinished(self):
        pass
### Part 1 End

def dualBoot(self):
        """Check if the device supports dual boot"""
        if getBoxType() == "et8500":
            rootfs2 = False
            kernel2 = False
            try:
                with open("/proc/mtd", "r") as f:
                    for line in f:
                        if 'rootfs2' in line:
                            rootfs2 = True
                        if 'kernel2' in line:
                            kernel2 = True
                return rootfs2 and kernel2
            except (IOError, OSError):
                print("[BackupSuite] Error reading /proc/mtd")
        return False

    def ForceMode(self):
        """Check if force mode is required for specific box models"""
        BOX_MODELS_FORCE_MODE = [
            "h9", "h9se", "h9combo", "h9combose", "i55plus", 
            "i55se", "h10", "hzero", "h8"
        ]
        return getBoxType() in BOX_MODELS_FORCE_MODE

    def getCurrentSelected(self):
        """Get the currently selected path in the file browser"""
        dirname = self.filelist.getCurrentDirectory()
        filename = self.filelist.getFilename()
        
        if not filename and not dirname:
            return ''
        elif not filename:
            return dirname
        elif not dirname:
            return filename
        else:
            if not self.filelist.canDescent() or len(filename) <= len(dirname):
                return dirname
            else:
                return filename

    def __selChanged(self):
        """Handle selection change in the file browser"""
        self["key_yellow"].setText("")
        self["key_green"].setText("")
        self["key_blue"].setText("")
        self["curdir"].setText(_("current:  %s") % (self.getCurrentSelected()))
        
        file_name = self.getCurrentSelected()
        try:
            if not self.filelist.canDescent() and file_name and file_name != '/':
                filename = self.filelist.getFilename()
                if filename and filename.endswith(".zip"):
                    self["key_yellow"].setText(_("Unzip"))
            elif self.filelist.canDescent() and file_name and file_name != '/':
                self["key_green"].setText(_("Run flash"))
                if os.path.isfile(file_name + LOGFILE) and os.path.isfile(file_name + VERSIONFILE):
                    self["key_yellow"].setText(_("Backup info"))
                    self["key_blue"].setText(_("Delete"))
        except Exception as e:
            print("[BackupSuite] Error in selection change:", e)

    def keyOk(self):
        """Handle OK button press"""
        if self.filelist.canDescent():
            self.filelist.descent()

    def confirmedWarning(self, result):
        """Callback after warning confirmation"""
        if result:
            self.founds = False
            self.showparameterlist()

    def keyGreen(self):
        """Handle green button press"""
        if self["key_green"].getText() == _("Run flash"):
            dirname = self.filelist.getCurrentDirectory()
            if dirname:
                warning_text = "\n"
                if self.dualboot:
                    warning_text += _("\nYou are using dual multiboot!")
                self.session.openWithCallback(
                    lambda r: self.confirmedWarning(r), 
                    MessageBox, 
                    _("Warning!\nUse at your own risk! Make always a backup before use!\nDon't use it if you use multiple ubi volumes in ubi layer!") + warning_text, 
                    MessageBox.TYPE_INFO
                )

    def showparameterlist(self):
        """Show flashing parameter options"""
        if self["key_green"].getText() != _("Run flash"):
            return
            
        dirname = self.getCurrentSelected()
        if not dirname:
            return
            
        model = getBoxType()
        
        # Define backup file configurations based on model
        backup_files = []
        no_backup_files = []
        text = _("Select parameter for start flash!\n")
        text += _('For flashing your receiver files are needed:\n')
        
        # Determine required files based on box model
        self._configureBackupFiles(model, backup_files, no_backup_files, text)
        
        try:
            self.founds = False
            text += _('\nThe found files:')
            
            # Look for backup files in the selected directory
            for name in os.listdir(dirname):
                if name in backup_files:
                    text += _("  %s (maybe ok)") % name
                    self.founds = True
                if name in no_backup_files:
                    text += _("  %s (maybe error)") % name
                    self.founds = True
                    
            if not self.founds:
                text += _(' nothing!')
        except Exception as e:
            print("[BackupSuite] Error scanning directory:", e)
            
        # Prepare options list based on findings
        if self.founds:
            open_list = [
                (_("Simulate (no write)"), "simulate"),
                (_("Standard (root and kernel)"), "standard"),
                (_("Only root"), "root"),
                (_("Only kernel"), "kernel"),
            ]
            open_list2 = [
                (_("Simulate second partition (no write)"), "simulate2"),
                (_("Second partition (root and kernel)"), "standard2"),
                (_("Second partition (only root)"), "rootfs2"),
                (_("Second partition (only kernel)"), "kernel2"),
            ]
            if self.dualboot:
                open_list += open_list2
        else:
            open_list = [
                (_("Exit"), "exit"),
            ]
            
        self.session.openWithCallback(self.Callbackflashing, MessageBox, text, simple=True, list=open_list)

    def _configureBackupFiles(self, model, backup_files, no_backup_files, text):
        """Configure backup files based on model - extracted to reduce complexity"""
        # DM-Series models
        if model.startswith("dm"):
            if "dm9" in model:
                backup_files.extend([("kernel.bin"), ("rootfs.tar.bz2")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("rootfs.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel.bin, rootfs.tar.bz2"
            elif model in ("dm520", "dm7080", "dm820"):
                backup_files.extend([("*.xz")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("rootfs.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("kernel_auto.bin"), ("kernel.bin"), ("rootfs.tar.bz2"), 
                                      ("uImage"), ("rootfs.ubi")])
                text += "*.xz"
            else:
                backup_files.extend([("*.nfi")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("rootfs.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("kernel_auto.bin"), ("kernel.bin"), ("rootfs.tar.bz2"), 
                                      ("uImage"), ("rootfs.ubi")])
                text += "*.nfi"
        # GB-Series models
        elif model.startswith("gb"):
            if "4k" not in model:
                backup_files.extend([("kernel.bin"), ("rootfs.bin")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("rootfs.tar.bz2"), ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel.bin, rootfs.bin"
            else:
                backup_files.extend([("kernel.bin"), ("rootfs.tar.bz2")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("rootfs.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel.bin, rootfs.tar.bz2"
        # VU+ models
        elif model.startswith("vu"):
            if "4k" in model:
                backup_files.extend([("kernel_auto.bin"), ("rootfs.tar.bz2")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("rootfs.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("kernel.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel_auto.bin, rootfs.tar.bz2"
            elif model in ("vuduo2", "vusolose", "vusolo2", "vuzero"):
                backup_files.extend([("kernel_cfe_auto.bin"), ("root_cfe_auto.bin")])
                no_backup_files.extend([("rootfs.bin"), ("root_cfe_auto.jffs2"), ("oe_kernel.bin"), 
                                      ("oe_rootfs.bin"), ("kernel.bin"), ("rootfs.tar.bz2"), 
                                      ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel_cfe_auto.bin, root_cfe_auto.bin"
            else:
                backup_files.extend([("kernel_cfe_auto.bin"), ("root_cfe_auto.jffs2")])
                no_backup_files.extend([("rootfs.bin"), ("root_cfe_auto.bin"), ("oe_kernel.bin"), 
                                      ("oe_rootfs.bin"), ("kernel.bin"), ("rootfs.tar.bz2"), 
                                      ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel_cfe_auto.bin, root_cfe_auto.jffs2"
        # Other box models - HD/UHD models
        else:
            # 4K models
            if model in ("hd51", "h7", "sf4008", "sf5008", "sf8008", "sf8008m", "vs1500", 
                         "et11000", "et13000", "bre2ze4k", "spycat4k", "spycat4kmini", 
                         "protek4k", "e4hdultra", "arivacombo", "arivatwin", "dual") or \
                model.startswith(("anadol", "axashis4", "dinobot4", "ferguson4", "mediabox4", "axashisc4")):
                backup_files.extend([("kernel.bin"), ("rootfs.tar.bz2")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("rootfs.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel.bin, rootfs.tar.bz2"
            # H9/H10/H8 family
            elif model in ("h9", "h9se", "h9combo", "h9combose", "i55plus", "i55se", "h10", "hzero", 
                           "h8", "dinobotu55", "iziboxx3", "dinoboth265", "axashistwin", "protek4kx1"):
                backup_files.extend([("uImage"), ("rootfs.ubi")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("rootfs.tar.bz2"), ("kernel_auto.bin"), ("kernel.bin"), ("rootfs.tar.bz2")])
                text += "uImage, rootfs.ubi"
            # HD60/HD61 family
            elif model in ("hd60", "hd61", "multibox", "multiboxse", "multiboxplus", "pulse4k", "pulse4kmini"):
                backup_files.extend([("uImage"), ("rootfs.tar.bz2")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("rootfs.ubi"), ("kernel_auto.bin"), ("kernel.bin")])
                text += "uImage, rootfs.tar.bz2"
            # ET models
            elif model.startswith(("et4", "et5", "et6", "et7", "et8", "et9", "et10")):
                backup_files.extend([("kernel.bin"), ("rootfs.bin")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("rootfs.tar.bz2"), ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel.bin, rootfs.bin"
            # EBOX models
            elif model.startswith("ebox"):
                backup_files.extend([("kernel_cfe_auto.bin"), ("root_cfe_auto.jffs2")])
                no_backup_files.extend([("rootfs.bin"), ("root_cfe_auto.bin"), ("oe_kernel.bin"), 
                                      ("oe_rootfs.bin"), ("kernel.bin"), ("rootfs.tar.bz2"), 
                                      ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel_cfe_auto.bin, root_cfe_auto.jffs2"
            # Various other brands
            elif model.startswith(("fusion", "pure", "optimus", "force", "iqon", "ios", 
                                  "tm2", "tmn", "tmt", "tms", "lunix", "mediabox", "vala")):
                backup_files.extend([("oe_kernel.bin"), ("oe_rootfs.bin")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("rootfs.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("kernel.bin"), ("rootfs.tar.bz2"), 
                                      ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "oe_kernel.bin, oe_rootfs.bin"
            # General 4K/UHD models
            elif "4k" in model or "uhd" in model:
                backup_files.extend([("oe_kernel.bin"), ("rootfs.tar.bz2")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("rootfs.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_rootfs.bin"), ("kernel.bin"), 
                                      ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "oe_kernel.bin, rootfs.tar.bz2"
            # Default for other models
            else:
                backup_files.extend([("kernel.bin"), ("rootfs.bin")])
                no_backup_files.extend([("kernel_cfe_auto.bin"), ("root_cfe_auto.jffs2"), 
                                      ("root_cfe_auto.bin"), ("oe_kernel.bin"), ("oe_rootfs.bin"), 
                                      ("rootfs.tar.bz2"), ("kernel_auto.bin"), ("uImage"), ("rootfs.ubi")])
                text += "kernel.bin, rootfs.bin"

    def Callbackflashing(self, ret):
        """Handle flashing parameter selection callback"""
        if not ret:
            return
            
        if ret == "exit":
            self.close()
            return
            
        # Check if recording is in progress
        if self.session.nav.RecordTimer.isRecording():
            self.session.open(
                MessageBox, 
                _("A recording is currently running. Please stop the recording before trying to start a flashing."), 
                MessageBox.TYPE_ERROR
            )
            self.founds = False
            return
            
        dir_flash = self.getCurrentSelected()
        text = _("Flashing: ")
        
        # Determine command based on selected option
        cmd = self._buildFlashCommand(ret, dir_flash, text)
        
        # Create message based on selected option and findings
        message = self._buildFlashMessage(ret)
        
        # Open console to execute flashing
        self.session.open(Console, text, [message, cmd])

    def _buildFlashCommand(self, ret, dir_flash, text):
        """Build flash command based on selected option - extracted to reduce complexity"""
        cmd = "echo -e"  # Default command
        
        # Simulation modes
        if ret == "simulate":
            text += _("Simulate (no write)")
            cmd = "%s -n '%s'" % (ofgwrite_bin, dir_flash)
        elif ret == "simulate2":
            text += _("Simulate second partition (no write)")
            cmd = "%s -kmtd3 -rmtd4 -n '%s'" % (ofgwrite_bin, dir_flash)
        # Standard flashing modes
        elif ret == "standard":
            text += _("Standard (root and kernel)")
            if self.ForceMode:
                cmd = "%s -f -r -k '%s' > /dev/null 2>&1 &" % (ofgwrite_bin, dir_flash)
            else:
                cmd = "%s -r -k '%s' > /dev/null 2>&1 &" % (ofgwrite_bin, dir_flash)
        elif ret == "standard2":
            text += _("Second partition (root and kernel)")
            cmd = "%s -kmtd3 -rmtd4 '%s' > /dev/null 2>&1 &" % (ofgwrite_bin, dir_flash)
        # Root-only modes
        elif ret == "root":
            text += _("Only root")
            cmd = "%s -r '%s' > /dev/null 2>&1 &" % (ofgwrite_bin, dir_flash)
        elif ret == "rootfs2":
            text += _("Second partition (only root)")
            cmd = "%s -rmtd4 '%s' > /dev/null 2>&1 &" % (ofgwrite_bin, dir_flash)
        # Kernel-only modes
        elif ret == "kernel":
            text += _("Only kernel")
            cmd = "%s -k '%s' > /dev/null 2>&1 &" % (ofgwrite_bin, dir_flash)
        elif ret == "kernel2":
            text += _("Second partition (only kernel)")
            cmd = "%s -kmtd3 '%s' > /dev/null 2>&1 &" % (ofgwrite_bin, dir_flash)
            
        return cmd

    def _buildFlashMessage(self, ret):
        """Build flash message based on selected option - extracted to reduce complexity"""
        if self.founds:
            if ret == "simulate" or ret == "simulate2":
                message = "echo -e '\n" + _('Show only found image and mtd partitions.\n') + "'"
            else:
                message = "echo -e '\n" + \
                         _('ofgwrite will stop enigma2 now to run the flash.\n') + \
                         _('Your STB will freeze during the flashing process.\n') + \
                         _('Please: DO NOT reboot your STB and turn off the power.\n') + \
                         _('The image or kernel will be flashing and auto booted in few minutes.\n') + \
                         "'"
        else:
            message = "echo -e '\n" + _('NOT found files for flashing!\n') + "'"
            
        return message

    def keyRed(self):
        """Handle red button press"""
        self.close()

    def keyYellow(self):
        """Handle yellow button press"""
        if self["key_yellow"].getText() == _("Unzip"):
            filename = self.filelist.getFilename()
            if filename and filename.endswith(".zip"):
                self.session.openWithCallback(
                    self.doUnzip, 
                    MessageBox, 
                    _("Do you really want to unpack %s ?") % filename, 
                    MessageBox.TYPE_YESNO
                )
        elif self["key_yellow"].getText() == _("Backup info"):
            try:
                backup_info = self.getBackupInfo()
                self.session.open(MessageBox, "\n\n\n%s" % backup_info, MessageBox.TYPE_INFO)
            except Exception as e:
                print("[BackupSuite] Error reading backup info:", e)
                self.session.open(MessageBox, _("Error reading backup information"), MessageBox.TYPE_ERROR)

    def getBackupInfo(self):
        """Get backup information from version file"""
        backup_dir = self.getCurrentSelected()
        backup_info = ""
        try:
            with open(backup_dir + VERSIONFILE, "r") as f:
                backup_info = f.read()
            return backup_info
        except (IOError, OSError) as e:
            print("[BackupSuite] Error reading version file:", e)
            return _("Could not read backup information")

    def doUnzip(self, answer):
        """Unzip the selected file if confirmed"""
        if answer is True:
            dirname = self.filelist.getCurrentDirectory()
            filename = self.filelist.getFilename()
            if dirname and filename:
                try:
                    os.system('unzip -o %s%s -d %s' % (dirname, filename, dirname))
                    self.filelist.refresh()
                except Exception as e:
                    print("[BackupSuite] Error during unzip:", e)

    def confirmedDelete(self, answer):
        """Delete backup if confirmed"""
        if answer is True:
            try:
                backup_dir = self.getCurrentSelected()
                cmdmessage = "echo -e 'Removing backup:   %s\n'" % os.path.basename(backup_dir.rstrip('/'))
                cmddelete = "rm -rf %s > /dev/null 2>&1" % backup_dir
                self.session.open(Console, _("Delete backup"), [cmdmessage, cmddelete], self.filelist.refresh)
            except Exception as e:
                print("[BackupSuite] Error during delete:", e)

    def KeyBlue(self):
        """Handle blue button press"""
        if self["key_blue"].getText() == _("Delete"):
            try:
                backup_info = self.getBackupInfo()
                self.session.openWithCallback(
                    self.confirmedDelete, 
                    MessageBox, 
                    _("You are about to delete this backup:\n\n%s\nContinue?") % backup_info, 
                    MessageBox.TYPE_YESNO
                )
            except Exception as e:
                print("[BackupSuite] Error preparing delete:", e)


def main(session, **kwargs):
    """Main function to start the plugin"""
    session.open(BackupStart)


def Plugins(path, **kwargs):
    """Register plugin in Enigma2"""
    global plugin_path
    plugin_path = path
    return [
        PluginDescriptor(
            name=_("BackupSuite"),
            description=_("Backup and restore your image") + ", " + versienummer,
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon='plugin.png',
            fnc=main
        ),
        PluginDescriptor(
            name=_("BackupSuite"),
            description=_("Backup and restore your image") + ", " + versienummer,
            where=PluginDescriptor.WHERE_EXTENSIONSMENU,
            fnc=main
        )
    ]

