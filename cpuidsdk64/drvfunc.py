#
# Copyright (C) 2025 remittor
#

import os
import sys
import inspect
import atexit
import struct
import ctypes
from ctypes.wintypes import *
from ctypes import byref
from ctypes import CFUNCTYPE

__author__ = 'remittor'

from cpuidsdk64 import *
from cpuidsdk64 import _get_drv

def ioctl_encode(DeviceType, Access, Function, Method):
    return (DeviceType << 16) | (Access << 14) | (Function << 2) | Method

def IOCTL(func_num):
    return ioctl_encode(CPUZ_DEVICE_TYPE, FILE_ANY_ACCESS, func_num, METHOD_BUFFERED)

def ioctl_decode(ioctl, ret_dict = False):
    DeviceType = (ioctl & 0xffff0000) >> 16
    Access     = (ioctl & 0x0000c000) >> 14
    Function   = (ioctl & 0x00003ffc) >> 2
    Method     = (ioctl & 0x00000003)
    if ret_dict:
        return { 'DeviceType': DeviceType, 'Access': Access, 'Function': Function, 'Method': Method }
    else:
        return f'DeviceType: 0x{DeviceType:X}, Access: 0x{Access:X}, Function: 0x{Function:X}, Method: 0x{Method:X}'

# ioctl: 9C402480 , 9C402484, 0x9C402488
def port_read(port, size):
    _drv = _get_drv()
    if size == 1:
        func_num = CPUZ_PORT_READ_1
    elif size == 2:
        func_num = CPUZ_PORT_READ_2
    elif size == 4:
        func_num = CPUZ_PORT_READ_4
    else:
        raise ValueError()
    inbuf = struct.pack('<I', port)
    buf = DeviceIoControl(_drv, IOCTL(func_num), inbuf, 8, None)
    val, rc = struct.unpack("<II", buf)
    if rc != 0x87654321:
        raise RuntimeError(f'ERROR: port_read: cannot read data from port = 0x{port:04X}')
    if size == 1:
        return val & 0xFF
    if size == 2:
        return val & 0xFFFF
    return val

def port_read_u1(port):
    return port_read(port, 1)

def port_read_u4(port):
    return port_read(port, 4)

# ioctl: 9C4024C0 , 9C4024C4 , 9C4024C8
def port_write(port, value, size = None):
    _drv = _get_drv()
    if isinstance(value, bytes):
        if size is not None and size != len(value):
            raise ValueError()
        size = len(value)
        value = int.from_bytes(value, 'little', signed = False)
    if size == 1:
        func_num = CPUZ_PORT_WRITE_1
    elif size == 2:
        func_num = CPUZ_PORT_WRITE_2
    elif size == 4:
        func_num = CPUZ_PORT_WRITE_4
    else:
        raise ValueError()
    inbuf = struct.pack('<II', port, value)
    buf = DeviceIoControl(_drv, IOCTL(func_num), inbuf, 8, None)
    rc = struct.unpack("<II", buf)
    return True if rc[0] == 0x87654321 and rc[1] == 0x87654321 else False

def port_write_u1(port, value):
    return port_write(port, value & 0xFF, 1)

def port_write_u4(port, value):
    return port_write(port, value & 0xFFFFFFFF, 4)


def CFG_ADDR(bus, dev, fun, reg):
    bus = SETDIM(bus, 15)
    dev = SETDIM(dev, 5)
    fun = SETDIM(fun, 3)
    reg = SETDIM(reg, 8)
    return 0x80000000 | (bus << 16) | (dev << 11) | (fun << 8) | reg

CFG_ADDR_PORT = 0xCF8
CFG_DATA_PORT = 0xCFC

# ioctl: 9C402700
def pci_cfg_read(bus, dev, fun, offset, size, method = 1):
    _drv = _get_drv()
    out_decimal = False
    if isinstance(size, str):
        out_decimal = True
        size = int(size)
    if size < 0:
        raise ValueError(f'Incorrect size argument')
    if method == 1:
        data_addr = 0
        if size > 0:
            data = bytearray(size)
            data_addr = get_bytes_addr(data)
        inbuf = struct.pack('<IIIIIII', bus, dev, fun, offset, size, HIDWORD(data_addr), LODWORD(data_addr))
        # BusDataType = PCIConfiguration  # 4
        # BusNumber = bus
        # SlotNumber = (SETDIM(fun, 3) << 5) | SETDIM(dev, 5)
        # Buffer = HIDWORD(data_addr) << 32 + LODWORD(data_addr)
        # Offset = offset
        # Length = size 
        # ULONG HalGetBusDataByOffset(BUS_DATA_TYPE BusDataType, ULONG BusNumber, ULONG SlotNumber, PVOID Buffer, ULONG Offset, ULONG Length);
        buf = DeviceIoControl(_drv, IOCTL(CPUZ_PCI_CFG_READ), inbuf, 4, None)
        if not buf or len(buf) != 4:
            raise RuntimeError(f'DeviceIoControl failed') # GetLastError
        sz = int.from_bytes(buf, 'little', signed = True)
        if sz == 2:
            #if size > 0:
            #    data = b'\xFF\xFF\xFF\xFF' * ((size - 1) // 4 + 1)
            return bytes(data) if not out_decimal else int.from_bytes(data, 'little')
        if sz == size:
            return bytes(data) if not out_decimal else int.from_bytes(data, 'little')
        return None
    if size == 0:
        raise ValueError(f'Incorrect size argument')
    buf = b''
    while len(buf) < size:
        addr = CFG_ADDR(bus, dev, fun, offset + len(buf))
        prev_state = port_read_u4(CFG_ADDR_PORT)
        try:
            port_write_u4(CFG_ADDR_PORT, addr & 0xFFFFFFFC)
            value = port_read_u4(CFG_DATA_PORT)
        finally:
            port_write_u4(CFG_ADDR_PORT, prev_state)
        value = value >> ((addr & 3) * 8)
        buf += struct.pack('<I', value)
    return buf if not out_decimal else int.from_bytes(buf, 'little')

# ioctl: 9C402704
def pci_cfg_write(bus, dev, fun, offset, data, method = 1):
    _drv = _get_drv()
    if isinstance(data, int):
        data_size = 4 if data <= 0xFFFFFFFF else 8
        data = data.to_bytes(data_size, 'little')
    if not data:
        raise ValueError(f'Incorrect data argument')
    if (len(data) & 3) != 0:
        raise ValueError(f'Incorrect data argument')
    if method == 1:
        size = len(data)
        data_addr = get_bytes_addr(data)
        inbuf = struct.pack('<IIIIIII', bus, dev, fun, offset, size, HIDWORD(data_addr), LODWORD(data_addr))
        # ULONG HalSetBusDataByOffset(BUS_DATA_TYPE BusDataType, ULONG BusNumber, ULONG SlotNumber, PVOID Buffer, ULONG Offset, ULONG Length);
        buf = DeviceIoControl(_drv, IOCTL(CPUZ_PCI_CFG_WRITE), inbuf, 4, None)
        if not buf or len(buf) != 4:
            raise RuntimeError(f'DeviceIoControl failed')
        rc = int.from_bytes(buf, 'little', signed = True)
        return True if rc != 0 else False
    pos = 0
    while pos < len(data):
        addr = CFG_ADDR(bus, dev, fun, offset + pos)
        if (addr & 3) != 0:
            raise ValueError(f'Incorrect offset argument')
        prev_state = port_read_u4(CFG_ADDR_PORT)
        try:
            port_write_u4(CFG_ADDR_PORT, addr & 0xFFFFFFFC)
            port_write_u4(CFG_DATA_PORT, data[pos:pos+4])
        finally:
            port_write_u4(CFG_ADDR_PORT, prev_state)
        pos += 4
    return True

def CFG_ADDR_EX(bus, dev, fun, off):
    bus = SETDIM(bus, 12)
    dev = SETDIM(dev, 5)
    fun = SETDIM(fun, 3)
    off = SETDIM(off, 12)
    return (bus << 20) | (dev << 15) | (fun << 12) | off

# ioctl: 9C402708
def pci_cfg_cmd(cfg_addr, value):
    _drv = _get_drv()
    inbuf = struct.pack('<II', cfg_addr, value)
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_PCI_CFG_CMD), inbuf, 4, None)
    if not buf or len(buf) != 4:
        raise RuntimeError(f'DeviceIoControl failed')
    return int.from_bytes(buf, 'little', signed = False)

# pci_cfg_read_ex    
def pci_cfg_command(bus, dev, fun, offset):
    addr = CFG_ADDR_EX(bus, dev, fun, offset)
    val = pci_cfg_read(bus, dev, fun, 0, 4);
    if not val:
        return None
    val = int.from_buffer(val, 'little')
    resp = pci_cfg_cmd(addr, val)
    return resp >> (8 * (addr & 3))

# ioctl: 0x9C402680     # for SPD addr = 0x50...0x53
def smbus_read_u1(port, dev, command, status = 0xBF):
    _drv = _get_drv()
    inbuf = struct.pack('<IIII', port, dev, command, status)
    # port_write_u1(port + SMBHSTSTS, status);
    # port_write_u1(port + SMBHSTADD, (dev << 1) | I2C_READ);
    # port_write_u1(port + SMBHSTCMD, command);
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_SMBUS_READ_1), inbuf, 16, None)
    ok, val, status, rc = struct.unpack('<IIII', buf)
    if ok == 1:
        return val & 0xFF
    if rc == 0xBB:  # Timed out (1000*10*20 ticks)
        print(f'ERROR: smbus_read_u1: timed out')
        return None
    if (status & 0x40) != 0:  # SMBHSTSTS_INUSE_STS = 0x40
        print('ERROR: smbus_read_u1: status = IN_USE')
    return None

# ioctl: 0x9C402690
def smbus_write_u1(port, dev, command, value, status = 0xBF):
    _drv = _get_drv()
    inbuf = struct.pack('<IIIII', port, dev, command, status, value)
    # port_write_u1(port, status);
    # port_write_u1(port + 4, dev << 1);
    # port_write_u1(port + 3, command);
    # port_write_u1(port + 5, value);
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_SMBUS_WRITE_1), inbuf, 8, None)
    ok, rc = struct.unpack('<II', buf)
    if ok == 1:
        return True
    if rc == 0x22222222:  # Timed out (1000*10*20 ticks)
        print(f'ERROR: smbus_write_u1: timed out')
        return False
    if rc == 0x33333333:  # DERR or BERR or FAIL
        print(f'ERROR: smbus_write_u1: DERR or BERR or FAIL')
        return False
    return False

# ioctl: 0x9C40269C    SMBHSTCNT_PROC_CALL    I2C_SMBUS_PROC_CALL
def smbus_pcall(port, dev, command, value, status = 0xBF):
    _drv = _get_drv()
    val_LO = value & 0xFF
    val_HI = (value >> 8) & 0xFF
    inbuf = struct.pack('<IIIIII', port, dev, command, status, val_LO, val_HI)
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_SMBUS_PCALL), inbuf, 16, None)
    ok, status, vLO, vHI = struct.unpack('<IIII', buf)
    if ok == 1:
        return (vHI << 8) + vLO
    if vLO == 0 and vHI == 0:  # Timed out (400*10*20 ticks)
        print(f'ERROR: smbus_pcall: timed out')
        return None
    if vLO == 1 and vHI == 0:  # DERR or BERR or FAIL
        print(f'ERROR: smbus_pcall: DERR or BERR or FAIL')
        return None
    return None

# ioctl: 0x9C402688
def smbus_read_X(port, dev, command):
    _drv = _get_drv()
    inbuf = struct.pack('<III', port, dev, command)
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_SMBUS_READ_X), inbuf, 16, None)
    ok, val, xxx, ticks = struct.unpack('<IIII', buf)
    if ok == 1:
        return val
    return None
    
#######################################################
#  MSR
#######################################################    
    
# ioctl: 9C402440
def msr_read(reg):
    _drv = _get_drv()
    inbuf = struct.pack('<I', reg)
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_MSR_READ), inbuf, 8, None)
    if not buf:
        return None
    val_LO, val_HI = struct.unpack('<II', buf)
    if val_LO == 0xFFFFFFFF and val_HI == 0xFFFFFFFF:
        return None
    return (val_HI << 32) + val_LO

# ioctl: 9C402444
def msr_write(reg, val_HI, val_LO):
    _drv = _get_drv()
    inbuf = struct.pack('<III', reg, val_HI, val_LO)
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_MSR_WRITE), inbuf, 8, None)
    if not buf:
        return False
    vLO, vHI = struct.unpack('<II', buf)
    if vLO != 0xAAAAAAAA or vHI != 0xBBBBBBBB:
        return False
    return True

# ioctl: 9C402448
def msr_oc_mailbox(cmd, data, method = 1):
    _drv = _get_drv()
    reg = 0x150  # MSR_OC_MAILBOX
    if method == 1:
        inbuf = struct.pack('<II', cmd, data)
        buf = DeviceIoControl(_drv, IOCTL(CPUZ_MSR_CMD), inbuf, 8, None)
        status, value = struct.unpack('<II', buf)
        #if val_LO == 0 and val_HI == 0:
        #    return None
        return status, value
    xvv = msr_read(reg)
    if xvv is not None:
        msr_write(reg, val_HI, val_LO)
        for tnum in range(0, 1000):
            kv = msr_read(addr)
            if kv is None:
                break
            if (kv[0] & 0x80000000) != 0:
                return kv
    return None        

# ioctl: 0x9C402608   msr_read
def msr_get_ticks(reg):
    _drv = _get_drv()
    inbuf = struct.pack('<I', reg)
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_MSR_GET_TICKS), inbuf, 8, None)
    ticks_HI, ticks_LO = struct.unpack('<II', buf)
    ticks = (ticks_HI << 32) + ticks_LO
    return ticks / 1000000
    
#######################################################
#  PHYS MEMORY
#######################################################    
    
# ioctl: 9C402540
def phymem_read(addr, size, out_decimal = False):
    _drv = _get_drv()
    if size <= 0:
        raise ValueError(f'Incorrect size argument')
    if not addr:
        raise ValueError()
    addr_HI = SETDIM(addr >> 32, 32)
    addr_LO = SETDIM(addr, 32)
    data = bytearray(size)
    data_addr = get_bytes_addr(data)
    inbuf = struct.pack('<IIIII', addr_HI, addr_LO, size, HIDWORD(data_addr), LODWORD(data_addr))
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_PHYMEM_READ), inbuf, 8, None)
    rc, data_addr_LO = struct.unpack('<II', buf)
    if rc == 0x11111111 or rc == 0x22222222 or rc == 0x33333333:
        return bytes(data) if not out_decimal else int.from_bytes(data, 'little')
    return None

# ioctl: 9C402544
def phymem_pc_read64(bus, dev, fun, offset, addr_mask, addr_offset):
    _drv = _get_drv()
    dev_fun = (SETDIM(dev, 5) << 3) | SETDIM(fun, 3)
    inbuf = struct.pack('<BBBBIII', 0, dev_fun, bus, 0, offset, addr_mask, addr_offset)
    # BusDataType = PCIConfiguration = 4
    # BusNumber = bus
    # SlotNumber = (SETDIM(fun, 3) << 5) | SETDIM(dev, 5)
    # Offset = offset
    # Length = 8
    # mem_addr = HalGetBusDataByOffset(BUS_DATA_TYPE BusDataType, ULONG BusNumber, ULONG SlotNumber, PVOID Buffer, ULONG Offset, ULONG Length);
    # mem_addr = mem_addr & addr_mask
    # mem_addr += addr_offset
    # value = *mem_addr
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_PHYMEM_PC_READ64), inbuf, 8, None)
    (value, ) = struct.unpack('<Q', buf)
    if value == 0xBBBBBBBBAAAAAAAA or value == 0xDDDDDDDDCCCCCCCC:
        return None
    return value

# ioctl: 9C402560
def phymem_pc_write32(bus, dev, fun, offset, addr_mask, addr_offset, value: int):
    _drv = _get_drv()
    dev_fun = (SETDIM(dev, 5) << 3) | SETDIM(fun, 3)
    inbuf = struct.pack('<BBBBIIII', 0, dev_fun, bus, 0, offset, addr_mask, addr_offset, value)
    # BusDataType = PCIConfiguration = 4
    # BusNumber = bus
    # SlotNumber = (SETDIM(fun, 3) << 5) | SETDIM(dev, 5)
    # Offset = offset
    # Length = 8
    # mem_addr = HalGetBusDataByOffset(BUS_DATA_TYPE BusDataType, ULONG BusNumber, ULONG SlotNumber, PVOID Buffer, ULONG Offset, ULONG Length);
    # mem_addr = mem_addr & addr_mask
    # mem_addr += addr_offset
    # *mem_addr = value 
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_PHYMEM_PC_WRITE32), inbuf, 4, None)
    (rc, ) = struct.unpack('<I', buf)
    if rc == 0xAAAAAAAA or rc == 0xCCCCCCCC:
        return False
    return True

# ioctl: 9C402550
def phymem_map(phy_addr, size):
    _drv = _get_drv()
    addr_HI = SETDIM(phy_addr >> 32, 32)
    addr_LO = SETDIM(phy_addr, 32)
    inbuf = struct.pack('<III', addr_HI, addr_LO, size)
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_PHYMEM_MAP), inbuf, 8, None)
    (map_addr, ) = struct.unpack('<Q', buf)
    if map_addr == 0:
        return None
    return map_addr

# ioctl: 9C402554
def phymem_unmap(phy_addr, size):
    _drv = _get_drv()
    addr_HI = SETDIM(phy_addr >> 32, 32)
    addr_LO = SETDIM(phy_addr, 32)
    inbuf = struct.pack('<III', addr_HI, addr_LO, size)
    buf = DeviceIoControl(_drv, IOCTL(CPUZ_PHYMEM_UNMAP), inbuf, 8, None)
    (rc0, rc1) = struct.unpack('<II', buf)
    if rc0 == 0x12345678 and rc1 == 0x87654321:
        return True
    return False

    