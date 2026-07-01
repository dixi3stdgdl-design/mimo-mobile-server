#!/bin/bash
# MiMo Mobile - Auto WiFi ADB Connect
# Automatically connects to Tab S9 and OnePlus 8 via WiFi when available
# Run this on startup or add to crontab

ADB="/home/DexTer/Android/Sdk/platform-tools/adb"
TAB_S9_IP="192.168.100.32"
ONEPLUS8_IP="192.168.100.166"
DEVICE_PORT="5555"
CHECK_INTERVAL=30

log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

ensure_usbipd_attach() {
    local busid=$1
    local name=$2
    if ! $ADB devices 2>/dev/null | grep -q "$name"; then
        log "$name not found via USB, attempting usbipd attach..."
        powershell.exe -Command "Start-Process -FilePath 'usbipd' -ArgumentList 'attach --wsl --busid $busid' -Verb RunAs -Wait" 2>/dev/null
        sleep 3
        if $ADB devices 2>/dev/null | grep -q "$name"; then
            log "USB attach successful for $name"
            return 0
        fi
        return 1
    fi
    return 0
}

enable_tcpip() {
    local serial=$1
    log "Enabling TCP/IP mode on $serial..."
    $ADB -s $serial tcpip $DEVICE_PORT 2>/dev/null
    sleep 2
}

connect_device() {
    local ip=$1
    local name=$2
    log "Connecting to $name at $ip:$DEVICE_PORT..."
    result=$($ADB connect $ip:$DEVICE_PORT 2>&1)
    if echo "$result" | grep -q "connected"; then
        log "$name WiFi ADB connected!"
        return 0
    else
        log "$name WiFi connection failed: $result"
        return 1
    fi
}

get_device_ip() {
    local serial=$1
    $ADB -s $serial shell ip addr show wlan0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1
}

connect_tab_s9() {
    log "=== Connecting Tab S9 ==="
    if $ADB devices 2>/dev/null | grep -q "device$"; then
        log "Tab S9 already connected"
        return 0
    fi
    
    connect_device $TAB_S9_IP "Tab S9"
    if [ $? -eq 0 ]; then return 0; fi
    
    ensure_usbipd_attach "1-2" "TABS900000000000231"
    if [ $? -eq 1 ]; then
        log "Tab S9 USB attach failed"
        return 1
    fi
    
    enable_tcpip $($ADB devices 2>/dev/null | grep "TABS900000000000231" | awk '{print $1}')
    local ip=$(get_device_ip $($ADB devices 2>/dev/null | grep "TABS900000000000231" | awk '{print $1}'))
    [ -n "$ip" ] && TAB_S9_IP=$ip
    connect_device $TAB_S9_IP "Tab S9"
}

connect_oneplus8() {
    log "=== Connecting OnePlus 8 ==="
    if $ADB devices 2>/dev/null | grep -q "OnePlus8"; then
        log "OnePlus 8 already connected"
        return 0
    fi
    
    connect_device $ONEPLUS8_IP "OnePlus 8"
    if [ $? -eq 0 ]; then return 0; fi
    
    ensure_usbipd_attach "1-3" "OnePlus8"
    if [ $? -eq 1 ]; then
        log "OnePlus 8 USB attach failed"
        return 1
    fi
    
    enable_tcpip $($ADB devices 2>/dev/null | grep "OnePlus8" | awk '{print $1}')
    local ip=$(get_device_ip $($ADB devices 2>/dev/null | grep "OnePlus8" | awk '{print $1}'))
    [ -n "$ip" ] && ONEPLUS8_IP=$ip
    connect_device $ONEPLUS8_IP "OnePlus 8"
}

main() {
    log "=== MiMo WiFi ADB Connect ==="
    
    connect_tab_s9
    connect_oneplus8
    
    log "=== Connected devices ==="
    $ADB devices -l
}

main "$@"
