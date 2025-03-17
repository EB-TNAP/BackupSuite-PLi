#!/bin/sh
if tty > /dev/null ; then
   RED='-e \e[00;31m'
   GREEN='-e \e[00;32m'
   YELLOW='-e \e[01;33m'
   BLUE='-e \e[00;34m'
   PURPLE='-e \e[01;31m'
   WHITE='-e \e[00;37m'
else
   RED='\c00??0000'
   GREEN='\c0000??00'
   YELLOW='\c00????00'
   BLUE='\c0000????'
   PURPLE='\c00?:55>7'
   WHITE='\c00??????'
fi

if [ -d "/usr/lib64" ]; then
	LIBDIR="/usr/lib64"
else
	LIBDIR="/usr/lib"
fi
PYVERSION=$(python3 -V 2>&1 | awk '{print $2}')
case $PYVERSION in
	2.*)
		PYEXT=pyo
		;;
	3.*)
		PYEXT=pyc
		;;
esac
if [ -z $PYVERSION ]; then
	echo "Unable to determine installed python3 version!"
	exit 1
fi

export LANG=$1
export HARDDISK=0
export SHOW="python3 $LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/message.$PYEXT $LANG"
TARGET=""
# Get used size of rootfs in one operation - more efficient
USEDSIZE=$(df -k /usr/ | awk 'NR==2 {print $3}')
NEEDEDSPACE=$(((4*$USEDSIZE)/1024))

# More efficient device detection - checks all mounts at once
mount_info=$(grep -E '^/dev/sd[a-z][0-9]+ /media/' /proc/mounts)

# Find backup device in one operation
while read -r device mountpoint fstype rest; do
    if [ -f "${mountpoint}/"*[Bb][Aa][Cc][Kk][Uu][Pp][Ss][Tt][Ii][Cc][Kk]* ] || [ -d "${mountpoint}/"*[Bb][Aa][Cc][Kk][Uu][Pp][Ss][Tt][Ii][Cc][Kk]* ]; then
        TARGET="${mountpoint}"
        break
    fi
done <<< "$mount_info"

# If no target found from mount_info, fall back to traditional method
if [ -z "$TARGET" ]; then
    for candidate in $(cut -d ' ' -f 2 /proc/mounts | grep '^/media/')
    do
        if [ -f "${candidate}/"*[Bb][Aa][Cc][Kk][Uu][Pp][Ss][Tt][Ii][Cc][Kk]* ] || [ -d "${candidate}/"*[Bb][Aa][Cc][Kk][Uu][Pp][Ss][Tt][Ii][Cc][Kk]* ]; then
            TARGET="${candidate}"
            break
        fi 
    done
fi

if [ -z "$TARGET" ] ; then
	echo -n $RED
	$SHOW "message21" #error about no USB-found
	echo -n $WHITE
else
	echo -n $YELLOW
	$SHOW "message22" 
	# Get size in a single operation
	read SIZE_2 SIZE_1 <<<$(df -h "$TARGET" | awk 'NR==2 {print $2, $4}')
	echo -n " -> $TARGET ($SIZE_2, " ; $SHOW "message16" ; echo "$SIZE_1)"
	FREESIZE=$(df -B 1048576 "$TARGET" | awk 'NR==2 {print $4}')
	if [ $FREESIZE -lt $NEEDEDSPACE ] ; then
		echo $RED
		$SHOW "message30" ; echo -n "$TARGET" ; $SHOW "message31"
		printf '%5s' $FREESIZE ; $SHOW "message32"
		printf '%5s' $NEEDEDSPACE ; $SHOW "message33"
		echo " "
		$SHOW "message34"
		echo $WHITE
		exit 0
	fi
	# Add parameters to improve backup performance
	chmod 755 $LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/backupsuite.sh > /dev/null 2>&1
	BS_OPTIONS="USB_SPEED=1 COMPRESS_LEVEL=1"
	$LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/backupsuite.sh "$TARGET" "$BS_OPTIONS"
	sync &  # Run sync in background
	exit 0
fi
