#
# Copyright (C) 2025 remittor
#

import os
import sys
import time
import struct
import ctypes as ct
import ctypes.wintypes as wintypes
from ctypes import byref
from types import SimpleNamespace
import json
import enum

__author__ = 'remittor'

from cpuinfo import *
from cpuidsdk64 import *
from hardware import *

# DOC: 13th Generation Intel ® Core™ Processor Datasheet, Volume 2 of 2
# ref: https://cdrdv2-public.intel.com/743846/743846-001.pdf

# DOC: 15th Generation Intel® Core™ Ultra 200S and 200HX Series Processors CFG & MEM Registers
# ref: https://edc.intel.com/output/DownloadCrifOutput?id=510

cpu_id = get_cpu_id()
MCHBAR_BASE = None
DMIBAR_BASE = None
gdict = { }

class DDR_TYPE(enum.IntEnum):
    def __new__(cls, value, name, doc = None):
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj._name_ = name
        obj.__doc__ = doc
        return obj
    DDR4   = 0, "DDR4"
    DDR5   = 1, "DDR5"
    LPDDR5 = 2, "LPDDR5"
    LPDDR4 = 3, "LPDDR4"

TREFIMIN_LPDDR  = 3904000   # Average periodic refresh interval, in picoseconds (3.904 us for LPDDR4/5)
TREFIMIN_DDR4   = 7800000   # Average periodic refresh interval, in picoseconds (7.8 us for DDR4)
TREFIMIN_DDR5   = 1950000   # Average periodic refresh interval, in picoseconds (1.95 us for DDR5)
TREFIMULTIPLIER = 1000      # tREFI value defined in XMP 1.3 spec is actually in thousands of MTB units. 

g_fake_cpu_id = None
g_fake_mchbar = None

SA_MC_BUS = 0
SA_MC_DEV = 0
SA_MC_FUN = 0
MCHBAR_ADDR_REG = 0x48
MCHBAR_ADDR_MASK = 0xFFFFFFFE


def phymem_read(addr, size, out_decimal = False):
    import cpuidsdk64
    global g_fake_mchbar
    if g_fake_mchbar and MCHBAR_BASE and addr >= MCHBAR_BASE and addr + size < MCHBAR_BASE + len(g_fake_mchbar):
        pos = addr - MCHBAR_BASE
        data = g_fake_mchbar[pos:pos+size]
        return int.from_bytes(data, 'little') if out_decimal else data
    return cpuidsdk64.phymem_read(addr, size, out_decimal)

def MrcReadCR(offset, size = 4):
    if size != 4 and size != 8:
        raise NotImplementedError()
    val = phymem_pc_read64(0, 0, 0, MCHBAR_ADDR_REG, MCHBAR_ADDR_MASK, offset)
    if val is None:
        return None
    if size == 4:
        return val & 0xFFFFFFFF
    return val

def MrcWriteCR(offset, value):
    rc = phymem_pc_write32(0, 0, 0, MCHBAR_ADDR_REG, MCHBAR_ADDR_MASK, offset, value & 0xFFFFFFFF)
    if not rc:
        print(f'ERROR: MrcWriteCR(0x{offset:X}): cannot write data to MCHBAR!')
        return False
    return True

def get_mchbar_info(info, controller, channel):
    global gdict, gcpuinfo, cpu_id, MCHBAR_BASE 
    MCHBAR_addr = MCHBAR_BASE + (0x10000 * controller)
    tm = { }    
    if True:
        MC_REGS_OFFSET = 0xE000
        MC_REGS_SIZE = 0x800
        offset = MC_REGS_OFFSET + (MC_REGS_SIZE * channel)
        data = phymem_read(MCHBAR_addr + offset, MC_REGS_SIZE)
        tm["__channel"] = channel
        
        IMC_CR_TC_CAS = 0x070     # CAS timing parameters
        tm["tCL"] = get_bits(data, IMC_CR_TC_CAS, 16, 22)
        tm["tCWL"] = get_bits(data, IMC_CR_TC_CAS, 24, 31)
        if cpu_id in i15_FAM:
            tm["tCCD_32_byte_CAS_delta"] = get_bits(data, IMC_CR_TC_CAS, 0, 5)
            
        IMC_CR_TC_PRE = 0         # Timing constraints to PRE commands
        tm["tRP"] = get_bits(data, IMC_CR_TC_PRE, 0, 7)
        if cpu_id in i12_FAM:
            tm["tRPab_ext"] = get_bits(data, IMC_CR_TC_PRE, 8, 12)
            tm["tRDPRE"] = get_bits(data, IMC_CR_TC_PRE, 13, 19)
            tm["tPPD"] = get_bits(data, IMC_CR_TC_PRE, 20, 23)
            tm["tRCDW"] = get_bits(data, IMC_CR_TC_PRE, 24, 31)
            tm["tWRPRE"] = get_bits(data, IMC_CR_TC_PRE, 32, 41)
            tm["tRAS"] = get_bits(data, IMC_CR_TC_PRE, 42, 50)
            tm["tRCD"] = get_bits(data, IMC_CR_TC_PRE, 51, 58)
            tm["DERATING_EXT"] = get_bits(data, IMC_CR_TC_PRE, 59, 62)
        if cpu_id in i15_FAM:
            tm["tRPab_ext"] = get_bits(data, IMC_CR_TC_PRE, 10, 17)
            tm["tRDPRE"] = get_bits(data, IMC_CR_TC_PRE, 20, 26)
            tm["tPPD"] = get_bits(data, IMC_CR_TC_PRE, 28, 31)
            tm["tWRPRE"] = get_bits(data, IMC_CR_TC_PRE, 33, 42)
            tm["tRAS"] = get_bits(data, IMC_CR_TC_PRE, 45, 53)
            tm["DERATING_EXT"] = get_bits(data, IMC_CR_TC_PRE, 59, 62)
        
        if cpu_id in i12_FAM:
            IMC_REFRESH_TC = 0x43C     # Refresh timing parameters
            tm["tREFI"] = get_bits(data, IMC_REFRESH_TC, 0, 17)
            tm["tRFC"]  = get_bits(data, IMC_REFRESH_TC, 18, 30)
            tm["tRFC2"] = None
            tm["tRFC4"] = None
        if cpu_id in i15_FAM:
            IMC_REFRESH_TC = 0x4A0     # Refresh timing parameters
            tm["tREFI"]    = get_bits(data, IMC_REFRESH_TC, 0, 17)
            tm["tRFC"]     = get_bits(data, IMC_REFRESH_TC, 18, 30)
            tm["tRFC2"] = None
            tm["tRFC4"] = None
            tm["tREFIx9"]  = get_bits(data, IMC_REFRESH_TC, 32, 39)
            tm["tRFCpb"]   = get_bits(data, IMC_REFRESH_TC, 40, 50)
            tm["tREFSBRD"] = get_bits(data, IMC_REFRESH_TC, 51, 58)
        
        IMC_REFRESH_AUX = 0x438
        tm["oref_ri"]  = get_bits(data, IMC_REFRESH_AUX, 0, 7)
        tm["REFRESH_HP_WM"]  = get_bits(data, IMC_REFRESH_AUX, 8, 11)
        tm["REFRESH_PANIC_WM"]  = get_bits(data, IMC_REFRESH_AUX, 12, 15)
        if cpu_id in i12_FAM:
            tm["COUNTTREFIWHILEREFENOFF"]  = get_bits(data, IMC_REFRESH_AUX, 16, 16)
            tm["HPREFONMRS"]  = get_bits(data, IMC_REFRESH_AUX, 17, 17)
            tm["SRX_REF_DEBITS"]  = get_bits(data, IMC_REFRESH_AUX, 18, 19)
            tm["RAISE_BLK_WAIT"]  = get_bits(data, IMC_REFRESH_AUX, 20, 23)
            tm["tREFIx9"]  = get_bits(data, IMC_REFRESH_AUX, 24, 31)   # Should be programmed to 8 * tREFI / 1024 (to allow for possible delays from ZQ or ISOC).
        if cpu_id in i12_FAM:
            IMC_REFRESH_EXT = 0x488
            tm["PBR_DISABLE"]  = get_bits(data, IMC_REFRESH_EXT, 0, 0)
            tm["PBR_OOO_DIS"]  = get_bits(data, IMC_REFRESH_EXT, 1, 1)
            tm["PBR_DISABLE_ON_HOT"]  = get_bits(data, IMC_REFRESH_EXT, 3, 3)
            tm["PBR_EXIT_ON_IDLE_CNT"]  = get_bits(data, IMC_REFRESH_EXT, 4, 9)
            tm["tRFCpb"]   = get_bits(data, IMC_REFRESH_EXT, 10, 20)
        
        tm["tRFM"]     = get_bits(data, 0x40C, 0, 10)    # Default is same as tRFCpb
        if cpu_id in i12_FAM:
            IMC_CR_TC_ACT = 0x008     # Timing constraints to ACT commands
            tm["tFAW"]     = get_bits(data, IMC_CR_TC_ACT, 0, 8)
            tm["tRRD_sg"]  = get_bits(data, IMC_CR_TC_ACT, 9, 14)
            tm["tRRD_dg"]  = get_bits(data, IMC_CR_TC_ACT, 15, 21)
            tm["tREFSBRD"] = get_bits(data, IMC_CR_TC_ACT, 24, 31)
        if cpu_id in i15_FAM:
            IMC_CR_TC_ACT = 0x138     # Timing constraints to ACT commands
            tm["tFAW"]     = get_bits(data, IMC_CR_TC_ACT, 0, 8)
            tm["tRRD_sg"]  = get_bits(data, IMC_CR_TC_ACT, 9, 14)
            tm["tRRD_dg"]  = get_bits(data, IMC_CR_TC_ACT, 15, 21)
            tm["tRCD"]     = get_bits(data, IMC_CR_TC_ACT, 22, 29)
            tm["tRCDW"]    = get_bits(data, IMC_CR_TC_ACT, 32, 39)
        tm["tRRD"] = None
        tm["tRRD_L"] = None
        tm["tRRD_S"] = None
        if info["DDR_TYPE"] in [ DDR_TYPE.DDR4, DDR_TYPE.DDR5 ]:
            tm["tRRD"]   = tm["tRRD_sg"]
            tm["tRRD_L"] = tm["tRRD_sg"]
            tm["tRRD_S"] = tm["tRRD_dg"]
        if info["DDR_TYPE"] in [ DDR_TYPE.LPDDR4, DDR_TYPE.LPDDR5 ]:
            tm["tRRD"]   = tm["tRRD_sg"]
            tm["tRRD_L"] = tm["tRRD_sg"]
        
        IMC_TC_PWDEN = 0x050     # Power Down Timing
        tm["tCKE"] = get_bits(data, IMC_TC_PWDEN, 0, 6)
        tm["tXP"] = get_bits(data, IMC_TC_PWDEN, 7, 13)
        if cpu_id in i12_FAM:
            tm["tXPDLL"] = get_bits(data, IMC_TC_PWDEN, 14, 20)
            tm["tRDPDEN"] = get_bits(data, IMC_TC_PWDEN, 21, 28)
            tm["tWRPDEN"] = get_bits(data, IMC_TC_PWDEN, 32, 41)
            tm["tCSH"] = get_bits(data, IMC_TC_PWDEN, 42, 47)
            tm["tCSL"] = get_bits(data, IMC_TC_PWDEN, 48, 53)
            tm["tPRPDEN"] = get_bits(data, IMC_TC_PWDEN, 59, 63)
        if cpu_id in i15_FAM:
            tm["tCPDED"] = get_bits(data, IMC_TC_PWDEN, 14, 18)
            tm["tRDPDEN"] = get_bits(data, IMC_TC_PWDEN, 19, 26)
            tm["tWRPDEN"] = get_bits(data, IMC_TC_PWDEN, 27, 36)
            tm["tCKCKEH"] = get_bits(data, IMC_TC_PWDEN, 37, 41)
            tm["tCSH"] = get_bits(data, IMC_TC_PWDEN, 42, 47)
            tm["tCSL"] = get_bits(data, IMC_TC_PWDEN, 48, 53)
            tm["tCACSH "] = get_bits(data, IMC_TC_PWDEN, 54, 58)
            tm["tPRPDEN"] = get_bits(data, IMC_TC_PWDEN, 59, 63)
        
        IMC_SC_GS_CFG = 0x088   # Scheduler configuration
        if cpu_id in i12_FAM:
            tm["CMD_STRETCH"] = get_bits(data, IMC_SC_GS_CFG, 3, 4)
            CR_map = { 0: "1N", 1: '2N', 2: '3N', 3: "N:1" }
            tm["tCR"] = CR_map[tm["CMD_STRETCH"]]
            tm["N_TO_1_RATIO"] = get_bits(data, IMC_SC_GS_CFG, 5, 7)
            tm["ADDRESS_MIRROR"] = get_bits(data, IMC_SC_GS_CFG, 8, 11)
            tm["GEAR4"] = get_bits(data, IMC_SC_GS_CFG, 15, 15)
            tm["NO_GEAR4_PARAM_DIVIDE"] = get_bits(data, IMC_SC_GS_CFG, 16, 16)
            tm["X8_DEVICE"] = get_bits(data, IMC_SC_GS_CFG, 28, 29)
            tm["NO_GEAR2_PARAM_DIVIDE"] = get_bits(data, IMC_SC_GS_CFG, 30, 30)
            tm["GEAR2"] = get_bits(data, IMC_SC_GS_CFG, 31, 31)
            tm["DDR_1DPC_SPLIT_RANKS_ON_SUBCH"] = get_bits(data, IMC_SC_GS_CFG, 32, 33)
            tm["WRITE0_ENABLE"] = get_bits(data, IMC_SC_GS_CFG, 49, 49)
            tm["WCKDIFFLOWINIDLE"] = get_bits(data, IMC_SC_GS_CFG, 54, 54)
            tm["tCPDED"] = get_bits(data, IMC_SC_GS_CFG, 56, 60)
        if cpu_id in i15_FAM:
            tm["CMD_STRETCH"] = get_bits(data, IMC_SC_GS_CFG, 3)
            tm["tCR"] = '1N' if tm["CMD_STRETCH"] == 0 else '2N'
            tm["ADDRESS_MIRROR"] = get_bits(data, IMC_SC_GS_CFG, 8, 11)
            tm["NO_GEAR4_PARAM_DIVIDE"] = get_bits(data, IMC_SC_GS_CFG, 16, 16)
            tm["NO_GEAR2_PARAM_DIVIDE"] = get_bits(data, IMC_SC_GS_CFG, 30, 30)
            tm["GEAR"] = 2 if get_bits(data, IMC_SC_GS_CFG, 31) == 0 else 4
            tm["DDR_1DPC_SPLIT_RANKS_ON_SUBCH"] = get_bits(data, IMC_SC_GS_CFG, 32, 33)
            tm["WRITE0_ENABLE"] = get_bits(data, IMC_SC_GS_CFG, 49, 49)
            tm["WCKDIFFLOWINIDLE"] = get_bits(data, IMC_SC_GS_CFG, 54, 54)
        
        if cpu_id in i12_FAM:
            tm["ALLOW_2CYC_B2B_LPDDR"] = get_bits(data, 0x00C, 7, 7)
        
        tm["tRDRD_sg"] = get_bits(data, 0x00C, 0, 6)
        tm["tRDRD_dg"] = get_bits(data, 0x00C, 8, 14)
        tm["tRDRD_dr"] = get_bits(data, 0x00C, 16, 23)
        tm["tRDRD_dd"] = get_bits(data, 0x00C, 24, 31)
        
        tm["tRDWR_sg"] = get_bits(data, 0x010, 0, 7)
        tm["tRDWR_dg"] = get_bits(data, 0x010, 8, 15)
        tm["tRDWR_dr"] = get_bits(data, 0x010, 16, 23)
        tm["tRDWR_dd"] = get_bits(data, 0x010, 24, 31)
        
        tm["tWRRD_sg"] = get_bits(data, 0x014, 0, 8)
        tm["tWRRD_dg"] = get_bits(data, 0x014, 9, 17)
        tm["tWRRD_dr"] = get_bits(data, 0x014, 18, 24)
        tm["tWRRD_dd"] = get_bits(data, 0x014, 25, 31)

        tm["tWRWR_sg"] = get_bits(data, 0x018, 0, 6)
        tm["tWRWR_dg"] = get_bits(data, 0x018, 8, 14)
        tm["tWRWR_dr"] = get_bits(data, 0x018, 16, 22)
        tm["tWRWR_dd"] = get_bits(data, 0x018, 24, 31)

        if cpu_id in i12_FAM:   # Self-Refresh Timing Parameters
            tm["tXSDLL"]  = get_bits(data, 0x440, 0, 12)
            tm["tZQOPER"] = get_bits(data, 0x440, 16, 23)   # UNDOC
            tm["tMOD"]    = get_bits(data, 0x440, 24, 31)   # UNDOC

        if cpu_id in i12_FAM:   # Self-Refresh Exit Timing Parameters 
            tm["tXSR"]    = get_bits(data, 0x4C0, 0, 12)
            tm["tSR"]     = get_bits(data, 0x4C0, 52, 57)
        if cpu_id in i15_FAM:   # Self-Refresh Exit Timing Parameters 
            tm["tXSR"]    = get_bits(data, 0x4C0, 0, 12)
            tm["tSR"]     = get_bits(data, 0x4C0, 45, 50)
            tm["tXSDLL"]  = get_bits(data, 0x4C0, 51, 63)
        
        if cpu_id in i12_FAM:
            tm["DEC_tCWL"] = get_bits(data, 0x478, 0, 5)   # The number of cycles (DCLK) decreased from tCWL.
            tm["ADD_tCWL"] = get_bits(data, 0x478, 6, 11)  # The number of cycles (DCLK) increased to tCWL.
            tm["ADD_1QCLK_DELAY"] = get_bits(data, 0x478, 12, 12)  # In Gear2, MC QCLK is actually 1xClk of the DDR, the regular MC register can only set even number of cycles (working in Dclk == 2 * 1xClk)

        if 'GEAR' not in tm:
            if tm['GEAR4']:
                tm['GEAR'] = 4
            elif tm['GEAR2']:
                tm['GEAR'] = 2
            else:
                tm['GEAR'] = 1

        tm["tRTL_0"] = get_bits(data, 0x020, 0, 7)
        tm["tRTL_1"] = get_bits(data, 0x020, 8, 15)
        tm["tRTL_2"] = get_bits(data, 0x020, 16, 23)
        tm["tRTL_3"] = get_bits(data, 0x020, 24, 31)

        if cpu_id in i12_FAM: # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # file "MrcMcRegisterStructAdlExxx.h"
            tm["enable_odt_matrix"] = get_bits(data, IMC_SC_GS_CFG, 24)
            IMC_CR_TC_ODT = 0x070
            tm["ODT_read_duration"] = get_bits(data, IMC_CR_TC_ODT, 0, 3)
            tm["ODT_Read_Delay"] = get_bits(data, IMC_CR_TC_ODT, 4, 7)
            tm["ODT_write_duration"] = get_bits(data, IMC_CR_TC_ODT, 8, 11)
            tm["ODT_Write_Delay"] = get_bits(data, IMC_CR_TC_ODT, 12, 15)
            tm["tAONPD"] = get_bits(data, IMC_CR_TC_ODT, 32, 37)
            tm["Write_Early_ODT"] = get_bits(data, IMC_CR_TC_ODT, 38)
            tm["PtrSep"] = get_bits(data, IMC_CR_TC_ODT, 39, 40)
            IMC_MISC_ODT = 0x0B4
            tm["ODT_Override"] = get_bits(data, IMC_MISC_ODT, 0, 3)
            tm["ODT_On"] = get_bits(data, IMC_MISC_ODT, 16, 19)
            tm["MPR_Train_DDR_On"] = get_bits(data, IMC_MISC_ODT, 31)
        
        IMC_ODT_Matrix = 0x080 # enabled using SC_GS_CFG_0_0_0_MCHBAR.enable_odt_matrix
        tm["READ_RANK_0"] = get_bits(data, IMC_ODT_Matrix, 0, 3)
        tm["READ_RANK_1"] = get_bits(data, IMC_ODT_Matrix, 4, 7)
        tm["READ_RANK_2"] = get_bits(data, IMC_ODT_Matrix, 8, 11)
        tm["READ_RANK_3"] = get_bits(data, IMC_ODT_Matrix, 12, 15)
        tm["WRITE_RANK_0"] = get_bits(data, IMC_ODT_Matrix, 16, 19)
        tm["WRITE_RANK_1"] = get_bits(data, IMC_ODT_Matrix, 20, 23)
        tm["WRITE_RANK_2"] = get_bits(data, IMC_ODT_Matrix, 24, 27)
        tm["WRITE_RANK_3"] = get_bits(data, IMC_ODT_Matrix, 28, 31)
        
        tm["DRAM_technology"] = get_bits(data, IMC_SC_GS_CFG, 0, 2)  # UNDOC !!!

        get_mrs_storage(data, tm, info, controller, channel)
        get_undoc_params(tm, info, controller, channel)
    else:
        raise RuntimeError(f'ERROR: Processor model 0x{cpu_id:X} not supported')
    return tm
    
def get_undoc_params(tm, info, controller, channel):
    global gdict, gcpuinfo, cpu_id
    mem = gdict['memory']
    mem_speed = 0
    if cpu_id in i12_FAM:
        mem_speed = mem['SA']['QCLK_FREQ'] * 2   # MT/s
    if cpu_id in i15_FAM:
        mem_speed = mem['QCLK_FREQ'] * 2
    mem["Speed"] = round(mem_speed, 2)
    mem["tCKmin"] = None
    # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # file "MrcInterface.h"
    if mem_speed > 0:
        mem["tCKmin"] = round(10**9 / (mem_speed / 2), 2)

    WritePost = None
    if tm['MRS'] and 'MR8' in tm['MRS']:
        WritePost = tm['MRS']['MR8']['WritePostambleSettings']

    # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # func "MrcSpdProcessing"
    if info["DDR_TYPE"] == DDR_TYPE.DDR4:
        info["BurstLength"] = 4   # BL8  - 8 UI's,  4 tCK
    elif info["DDR_TYPE"] == DDR_TYPE.DDR5:
        info["BurstLength"] = 8   # BL16 - 16 UI's, 8 tCK
    elif info["DDR_TYPE"] == DDR_TYPE.LPDDR4:
        info["BurstLength"] = 16  # BL32 - 32 UI's, 16 tCK
    elif info["DDR_TYPE"] == DDR_TYPE.LPDDR5:
        info["BurstLength"] = 4   # BL32 - tCK in 4:1 is 8 UI's per clock, 4tCK

    # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # func "SetTcTurnAround"
    # TatDelta = 0
    # tWRRD_sg = Timing->tCWL + BurstLength + tWTR_L + 2 + TatDelta;
    # tWRRD_dg = Timing->tCWL + BurstLength + tWTR_S + 2 + TatDelta;
    tm["tWTR_L"] = tm['tWRRD_sg'] - tm['tCWL'] - info["BurstLength"] - 2
    tm["tWTR_S"] = tm['tWRRD_dg'] - tm['tCWL'] - info["BurstLength"] - 2

    if cpu_id in (i13_CPU + i14_CPU) and info["DDR_TYPE"] == DDR_TYPE.DDR5 and mem_speed >= 5200:
        # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # func "SetTcTurnAround"
        if WritePost is not None:
            if tm["tWTR_L"] >= 2:
                tm["tWTR_L"] -= WritePost
            if tm["tWTR_S"] >= 2:
                tm["tWTR_S"] -= WritePost
    
    if 'DEC_tCWL' in tm and tm['DEC_tCWL'] is not None:  # ASRock Timing Configurator
        xCWL = tm['tCWL']
        xCWL -= tm['DEC_tCWL']  # UNDOC
        xCWL += tm['ADD_tCWL']  # UNDOC
        tm["tWTR_L_alt"] = tm['tWRRD_sg'] - xCWL - info["BurstLength"] - 2
        tm["tWTR_S_alt"] = tm['tWRRD_dg'] - xCWL - info["BurstLength"] - 2

    tm["FineGranularityRefresh"] = None
    if False:
        # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # func "MrcSetupMrcData"
        tm["FineGranularityRefresh"] = False
        if tm["REFRESH_HP_WM"] == 4 and tm["REFRESH_PANIC_WM"] == 5:
            tm["FineGranularityRefresh"] = False
    
    if tm['MRS'] and 'MR4' in tm['MRS']:
        # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # func "Ddr5JedecInitVal"
        tm["FineGranularityRefresh"] = True if tm['MRS']['MR4']['RefreshTrfcMode'] else False

    if info["DDR_TYPE"] == DDR_TYPE.DDR5 and tm["FineGranularityRefresh"] == True:
        tRFC = tm["tRFC"]
        tm["tRFC"] = None
        tm["tRFC2"] = tRFC  # Fine Granularity Refresh mode uses tRFC2 

    if True:
        # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # func "SetTcPreActOdt"
        tm['tRTP'] = tm['tRDPRE']
        if tm["tCR"] == '2N': # SubtractOneClock
            tm['tRTP'] += 1
        if tm['tRTP'] in [ 13, 16, 19, 22 ]:
            # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # func "GetDdr5tRTP"
            # 13, 16, 19, 22 are not valid values, use the next one
            tm['tRTP'] += 1

    ''' # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # func "SetTcPreActOdt"
      // tWRPRE is = tCWL + BLn/2 + tWR
      tWRPRE = Timing->tCWL + Outputs->BurstLength + Timing->tWR;
      // LPDDR adds an addition clock
      // LPDDR5 - 4.10.4 Timing constraints for 8Bank Mode (BL32 only)
      if (Lpddr) {
        tWRPRE++;
      }
      if (Lpddr5) {
        tWRPRE = ((INT32) tWRPRE) * 4;
      }
      SubtractOneClock = Ddr5 && (Timing->NMode == 2);
      if (SubtractOneClock) {
        tWRPRE--;
      }
      tWRPRE = RANGE (tWRPRE, tWRPRE_MIN, tWRPRE_MAX);       
    '''
    tWRPRE_MIN = 18  # < minimum tWRPRE (Write->PRE) supported in tCK/wCK
    tWRPRE_MAX = 200 # < maximum tWRPRE (Write->PRE) supported in tCK/wCK
    tm['tWR'] = tm['tWRPRE'] - tm['tCWL'] - info["BurstLength"]
    if info["DDR_TYPE"] == DDR_TYPE.DDR4:
        pass
    elif info["DDR_TYPE"] == DDR_TYPE.DDR5:
        if tm["tCR"] == '2N': # SubtractOneClock
            tm['tWR'] += 1
        # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # func "tWRPDENValue"
        # tWRPDEN = tCWL + MRC_DDR5_tCCD_ALL_FREQ  + tWR + 1;
        MRC_DDR5_tCCD_ALL_FREQ = 8  # CAS-to-CAS delay for all frequencies in tCK
        tm['tWR__a'] = tm['tWRPDEN'] - tm['tCWL'] - MRC_DDR5_tCCD_ALL_FREQ - 1
    elif info["DDR_TYPE"] == DDR_TYPE.LPDDR5:
        tm['tWR'] = tm['tWRPRE'] // 4 - tm['tCWL'] - info["BurstLength"] - 1
    elif info["DDR_TYPE"] == DDR_TYPE.LPDDR4:
        tm['tWR'] -= 1
    else:
        raise RuntimeError()

    rev_A0 = None
    Q0Regs = None
    if cpu_id in [ CPUID.ALDERLAKE ] and gcpuinfo['stepping'] in [ 0, 1 ]:
        Q0Regs = False  # for ADL with stepping A0 or B0
    
    if True:
        DATA_CR_DQSTXRXCTL_REG = 0x84A0
        data = MrcReadCR(DATA_CR_DQSTXRXCTL_REG)   # struct DATA0CH0_CR_DQSTXRXCTL_STRUCT
        dcr = { }
        dcr['dqstx_cmn_txvttparkendqsp'] = get_bits(data, 0, 0)
        dcr['dqstx_cmn_txdqsprnfdelay'] = get_bits(data, 0, 1, 5)
        dcr['dqstx_cmn_txdqspfnrdelay'] = get_bits(data, 0, 6, 10)
        dcr['dqstx_cmn_txvttparkendqsn'] = get_bits(data, 0, 11)
        dcr['dqstx_cmn_txvsshiffstlegen'] = get_bits(data, 0, 12)
        dcr['dqstx_cmn_txodtstatlegendqs'] = get_bits(data, 0, 13)
        dcr['dqstx_cmn_txidlemodedrven'] = get_bits(data, 0, 14)
        dcr['bonus_1'] = get_bits(data, 0, 15)
        rev_A0 = True if dcr['bonus_1'] else False
        if rev_A0:
            Q0Regs = False
        else:    
            Q0Regs = False if dcr['dqstx_cmn_txdqsprnfdelay'] == 0x10 else True

    VccDD2 = None
    if True:
        DDRPHY_COMP_CR_DLLCOMP_VDLLCTRL_REG = 0x2C54
        data = MrcReadCR(DDRPHY_COMP_CR_DLLCOMP_VDLLCTRL_REG)   # struct DDRPHY_COMP_CR_DLLCOMP_VDLLCTRL_STRUCT
        vdll = { }
        vdll['dllcomp_cmn_vdlltargdaccode'] = get_bits(data, 0, 0, 7)
        vdll['dllcomp_cmn_vdlllodaccode'] = get_bits(data, 0, 8, 15)
        vdll['dllcomp_cmn_vdllhidaccode'] = get_bits(data, 0, 16, 23)
        vdll['vdllcomprxrstb'] = get_bits(data, 0, 24)
        vdll['vdllcompareen'] = get_bits(data, 0, 25)
        vdll['bonus6'] = get_bits(data, 0, 26, 31)
        if vdll['dllcomp_cmn_vdlllodaccode']: 
            # dllcomp_cmn_vdlllodaccode = 256 * (0.45 / param.VCCDD2);  # ref: ICÈ_TÈA_BIOS  func: MrcPhyInitCompStaticCompInit
            VccDD2 = round(256 * 0.45 / vdll['dllcomp_cmn_vdlllodaccode'], 3)

    VccIO = None
    if not VccDD2:
        try:
            VccIO = gdict['MSR']['BIOS']['VccIO']
        except KeyError:
            import biosbox
            bmb = biosbox.BiosMailBox()
            VccIO = bmb.get_vccio_value()
        mem['VccIO'] = VccIO

    if True:
        DDRPHY_COMP_NEW_CR_VSSHICOMP_CTRL2_REG = 0x3CA0
        data = MrcReadCR(DDRPHY_COMP_NEW_CR_VSSHICOMP_CTRL2_REG)   # struct DDRPHY_COMP_NEW_CR_VSSHICOMP_CTRL2_STRUCT
        new = { }
        new['vsshicompcr_dqvrefcode']   = get_bits(data, 0, 0, 7)
        new['vsshicompcr_cmdvrefcode']  = get_bits(data, 0, 8, 15)
        new['vsshicompcr_rxvrefcode']   = get_bits(data, 0, 16, 23)
        new['vsshicompcr_leakvrefcode'] = get_bits(data, 0, 24, 31)
        if new['vsshicompcr_dqvrefcode'] > 0:
            if new['vsshicompcr_dqvrefcode'] == new['vsshicompcr_cmdvrefcode'] == new['vsshicompcr_rxvrefcode'] == new['vsshicompcr_leakvrefcode']:
                if VccDD2:
                    # ref: vsshicompcr_dqvrefcode = (192 * min(0.3,(param.VCCDD2 - param.VCCIO)) / param.VCCDD2)   # func: MrcPhyInitSeq1
                    VccIO_alt = round( (1 - new['vsshicompcr_dqvrefcode'] / 192) * VccDD2, 3)
                    if VccIO:
                        mem['VccIO_alt'] = VccIO_alt
                    else:
                        VccIO = VccIO_alt
                        mem['VccIO'] = VccIO
                elif VccIO:
                    VccDD2 = round( VccIO / ( 1 - new['vsshicompcr_dqvrefcode'] / 192), 3)

    if VccDD2:
        mem['VccDD2'] = VccDD2

    if VccDD2 and Q0Regs:
        DDRPHY_COMP_CR_VCCDDQLDO_DVFSCOMP_CTRL0_REG = 0x2C30
        data = MrcReadCR(DDRPHY_COMP_CR_VCCDDQLDO_DVFSCOMP_CTRL0_REG)   # struct DDRPHY_COMP_CR_VCCDDQLDO_DVFSCOMP_CTRL0_STRUCT
        vddq = { }
        vddq['vccddq_lvrcoderes1'] = get_bits(data, 0, 0, 3)
        vddq['vccddq_lvrcoderes2'] = get_bits(data, 0, 4, 7)
        vddq['rxdqscomp_cmn_rxvcdlcben'] = get_bits(data, 0, 8, 9)
        vddq['vccddq_lvrcodelvrleg'] = get_bits(data, 0, 10, 13)
        vddq['vccddq_lvrtargetcode'] = get_bits(data, 0, 14, 19)   # 6 bits (0...63)
        vddq['vccddq_lvrbiasvrefsel'] = get_bits(data, 0, 20, 22)
        vddq['vccddq_lvrbypass'] = get_bits(data, 0, 23)
        vddq['vccddq_lvrlsbypass'] = get_bits(data, 0, 24)
        vddq['vccddq_lvrmuxtristate'] = get_bits(data, 0, 25)
        vddq['vccddq_lvrovrden'] = get_bits(data, 0, 26)
        vddq['periodiccomp_lvrmuxvccddqgsel'] = get_bits(data, 0, 27)
        vddq['dvfscomp_lvrmuxvccddqgsel'] = get_bits(data, 0, 28)
        vddq['Spare'] = get_bits(data, 0, 29, 31)
        # vccddq_lvrtargetcode = ((96 * Outputs->VccddqVoltage) / Vdd2Mv) - 26;  # ref: ICÈ_TÈA_BIOS  func: MrcPhyInitCompStaticCompInit
        VccddqVoltage = round((vddq['vccddq_lvrtargetcode'] + 26) * VccDD2 / 96, 3)
        if VccddqVoltage < 0.648:
            VccddqVoltage = round((vddq['vccddq_lvrtargetcode'] + 64 + 26) * VccDD2 / 96, 3)
        mem['VccDDQ'] = VccddqVoltage   # IVR VDDQ TX

# -----------------------------------------------------------------------------------------------------------

def OdtDecode(value):
    if value == 0:
        return 0   # Disabled, Reset default
    Ohm_list = [  0,  240,     120,     80,      60,      48,      40,      34     ]
    RZQ_list = [ '', 'RZQ/1', 'RZQ/2', 'RZQ/3', 'RZQ/4', 'RZQ/5', 'RZQ/6', 'RZQ/7' ]
    return Ohm_list[value] if value < len(Ohm_list) else None

def CccOdtDecode(value):
    if value == 0:
        return 0   # Disabled, Reset default
    Ohm_list = [  0,  480,     240,     120,     80,      60,      48,      40,    ]
    RZQ_list = [ '', 'RZQ*2', 'RZQ/1', 'RZQ/2', 'RZQ/3', 'RZQ/4', 'RZQ/5', 'RZQ/6' ]
    return Ohm_list[value] if value < len(Ohm_list) else None

def VrefPercentDecode(index):  # ref: ICÈ_TÈA_BIOS enum DDR5_MR10_VREF
    return 97.5 - index / 2

def DDR5_ImpedanceDecode(value):
    val_list = [ 34, 40, 48 ]
    return val_list[value] if value < len(val_list) else None

def DDR5_MR0_decode(value):
    res = { }
    BL_map = [ 'BL16', 'BC8 OTF', 'BL32', 'BL32 OTF' ]
    res['BurstLength'] = BL_map[get_bits(value, 0, 0, 1)]
    res['CasLatency'] = 22 + 2 * get_bits(value, 0, 2, 6)
    return res

def DDR5_MR2_decode(value):
    res = { }
    res['ReadPreambleTraining']  = get_bits(value, 0, 0)
    res['WriteLevelingTraining'] = get_bits(value, 0, 1)
    res['Mode1n']                = get_bits(value, 0, 2)
    res['MaxPowerSavingsMode']   = get_bits(value, 0, 3)
    res['CsAssertionDuration']   = get_bits(value, 0, 4)
    res['Device15Mpsm']          = get_bits(value, 0, 5)
    res['InternalWriteTiming']   = get_bits(value, 0, 7)
    return res

def DDR5_MR4_decode(value):
    res = { }
    res['RefreshRate'] = get_bits(value, 0, 0, 2)
    res['RefreshTrfcMode'] = get_bits(value, 0, 4)
    res['Tuf'] = get_bits(value, 0, 7)
    return res

def DDR5_MR5_decode(value):
    res = { }
    res['DataOutputDisable'] = get_bits(value, 0, 0)
    res['PullUpOutputDriverImpedance'] = DDR5_ImpedanceDecode(get_bits(value, 0, 1, 2))
    res['PackageOutputDriverTestModeSupported'] = get_bits(value, 0, 3)
    res['TDQS_Enable'] = get_bits(value, 0, 4)
    res['DM_Enable'] = get_bits(value, 0, 5)
    res['PullDownOutputDriverImpedance'] = DDR5_ImpedanceDecode(get_bits(value, 0, 6, 7))
    return res

def DDR5_MR6_decode(value):
    RTP_map = [ 12, 14, 15, 17, 18, 20, 21, 23, 24, None, None, None, None, None, None, None ]
    res = { }
    res['WriteRecoveryTime'] = 48 + 6 * get_bits(value, 0, 0, 3)
    res['tRTP'] = RTP_map[get_bits(value, 0, 4, 7)]
    return res

def DDR5_MR8_decode(value):
    res = { }
    res['ReadPreambleSettings']   = get_bits(value, 0, 0, 2)
    res['WritePreambleSettings']  = get_bits(value, 0, 3, 4)
    res['ReadPostambleSettings']  = get_bits(value, 0, 6)
    res['WritePostambleSettings'] = get_bits(value, 0, 7)
    return res

def DDR5_MR10_decode(value):
    return VrefPercentDecode( get_bits(value, 0, 0, 7) )

def DDR5_MR11_decode(value):
    return VrefPercentDecode( get_bits(value, 0, 0, 7) & 0x7F )

def DDR5_MR12_decode(value):
    return VrefPercentDecode( get_bits(value, 0, 0, 7) & 0x7F )

def DDR5_MR13_decode(value):
    value = value & 0x0F
    mr13_table = {
        0 : { 'tCCD_L': 8,  'tCCD_L_WR': 16, 'tCCD_L_WR2': 32, 'tDDLK': 1024, 'speed': [ 1980, 3200 ] },
        1 : { 'tCCD_L': 9,  'tCCD_L_WR': 18, 'tCCD_L_WR2': 36, 'tDDLK': 1024, 'speed': [ 3200, 3600 ] },
        2 : { 'tCCD_L': 10, 'tCCD_L_WR': 20, 'tCCD_L_WR2': 40, 'tDDLK': 1280, 'speed': [ 3600, 4000 ] },
        3 : { 'tCCD_L': 11, 'tCCD_L_WR': 22, 'tCCD_L_WR2': 44, 'tDDLK': 1280, 'speed': [ 4000, 4400 ] },
        4 : { 'tCCD_L': 12, 'tCCD_L_WR': 24, 'tCCD_L_WR2': 48, 'tDDLK': 1536, 'speed': [ 4400, 4800 ] },
        5 : { 'tCCD_L': 13, 'tCCD_L_WR': 26, 'tCCD_L_WR2': 52, 'tDDLK': 1536, 'speed': [ 4800, 5200 ] },
        6 : { 'tCCD_L': 14, 'tCCD_L_WR': 28, 'tCCD_L_WR2': 56, 'tDDLK': 1792, 'speed': [ 5200, 5600 ] },
        7 : { 'tCCD_L': 15, 'tCCD_L_WR': 30, 'tCCD_L_WR2': 60, 'tDDLK': 1792, 'speed': [ 5600, 6000 ] },
        8 : { 'tCCD_L': 16, 'tCCD_L_WR': 32, 'tCCD_L_WR2': 64, 'tDDLK': 2048, 'speed': [ 6000, 6400 ] },
        9 : { 'tCCD_L': 17, 'tCCD_L_WR': 34, 'tCCD_L_WR2': 68, 'tDDLK': 2048, 'speed': [ 6400, 6800 ] },
        10: { 'tCCD_L': 18, 'tCCD_L_WR': 36, 'tCCD_L_WR2': 72, 'tDDLK': 2304, 'speed': [ 6800, 7200 ] },
        11: { 'tCCD_L': 19, 'tCCD_L_WR': 38, 'tCCD_L_WR2': 76, 'tDDLK': 2304, 'speed': [ 7200, 7600 ] },
        12: { 'tCCD_L': 20, 'tCCD_L_WR': 40, 'tCCD_L_WR2': 80, 'tDDLK': 2560, 'speed': [ 7600, 8000 ] },
        13: { 'tCCD_L': 21, 'tCCD_L_WR': 42, 'tCCD_L_WR2': 84, 'tDDLK': 2560, 'speed': [ 8000, 8400 ] },
        14: { 'tCCD_L': 22, 'tCCD_L_WR': 44, 'tCCD_L_WR2': 88, 'tDDLK': 2816, 'speed': [ 8400, 8800 ] },    
    }
    if value >= len(mr13_table):
        return None
    return mr13_table[value]

def DDR5_MR14_decode(value):
    res = { }
    res['Cid0'] = get_bits(value, 0, 0)
    res['Cid1'] = get_bits(value, 0, 1)
    res['Cid2'] = get_bits(value, 0, 2)
    res['Cid3'] = get_bits(value, 0, 3)
    res['RowMode_CodeWordMode'] = get_bits(value, 0, 5)
    res['ResetEcsCounter']      = get_bits(value, 0, 6)
    res['EcsMode']              = get_bits(value, 0, 7)
    return res

def DDR5_MR32_decode(value):
    res = { }
    res['CK'] = CccOdtDecode(get_bits(value, 0, 0, 2))
    res['CS'] = CccOdtDecode(get_bits(value, 0, 3, 5))
    res['CA_Strap'] = get_bits(value, 0, 6)
    return res

def DDR5_MR33_decode(value):
    res = { }
    res['CA'] = CccOdtDecode(get_bits(value, 0, 0, 2))
    res['RttParkDqs'] = OdtDecode(get_bits(value, 0, 3, 5))
    return res

# enum GmfCmdType
GmfCmdMrw  = 0
GmfCmdMpc  = 1
GmfCmdVref = 2

def FSM_decode(value):
    # struct MC0_CH0_CR_GENERIC_MRS_FSM_CONTROL_0_STRUCT
    res = { }
    res['ADDRESS']        = get_bits(value, 0, 0, 7)
    res['MRS_STOR_PTR']   = get_bits(value, 0, 8, 16)    # GENERIC_MRS_STORAGE_POINTER
    res['COMMAND_TYPE']   = get_bits(value, 0, 22, 23)   # enum GmfCmdType
    res['GmfTimingIndex'] = get_bits(value, 0, 24, 25)   # enum GmfTimingIndex / DelayIndex / TIMING_VALUE_POINTER
    res['PER_DEVICE']     = get_bits(value, 0, 27)
    res['FSP_CONTROL']    = get_bits(value, 0, 28, 29)
    res['PER_RANK']       = get_bits(value, 0, 30)
    res['ACTIVE']         = get_bits(value, 0, 31)
    return res

def get_mrs_storage(data, tm, info, controller, channel):
    global gdict, cpu_id
    # ref: ICÈ_TÈA_BIOS  (leaked BIOS sources)  # file "MrcMcRegisterStructAdlExxx.h" + "MrcDdr5Registers.h"
    IMC_MRS_FSM_STORAGE = 0x200    # 0xE200
    IMC_FSM_STORAGE     = 0x600    # 0xE600
    MAX_MR_GEN_FSM          = 108  # Maximum number of MRS FSM CONTROL MR Addresses that can be sent.
    GEN_MRS_FSM_STORAGE_MAX = 60   # 60 Storage registers
    GEN_MRS_FSM_BYTE_MAX    = 240  # 60 Registers * 4 Bytes per register         
    
    mrs_data_size = IMC_FSM_STORAGE - IMC_MRS_FSM_STORAGE
    mrs_data = data[IMC_MRS_FSM_STORAGE : IMC_MRS_FSM_STORAGE + mrs_data_size]
    mrs_list = [ get_bits(mrs_data, i, 0, 7) for i in range(0, len(mrs_data)) ]
    
    fsm_data_size = MAX_MR_GEN_FSM * 4
    fsm_data = data[IMC_FSM_STORAGE : IMC_FSM_STORAGE + fsm_data_size]
    fsm_list = [ get_bits(fsm_data, i, 0, 31) for i in range(0, len(fsm_data), 4) ]

    fsm_len = 0
    mrs_size = 0

    def find_MR_into_FSM(MR_num, cmd_type = GmfCmdMrw, active = None):
        nonlocal fsm_list, fsm_len, mrs_list, mrs_size
        for pos, val in enumerate(fsm_list):
            if fsm_len > 0 and pos >= fsm_len:
                break
            fsm = FSM_decode(val)
            if fsm["ADDRESS"] == MR_num and fsm['COMMAND_TYPE'] == cmd_type:
                if active is None or fsm['ACTIVE'] == active:
                    next_fsm = FSM_decode(fsm_list[pos + 1])
                    if next_fsm['MRS_STOR_PTR'] < fsm['MRS_STOR_PTR']:
                        fsm['size'] = None
                    else:
                        fsm['size'] = next_fsm['MRS_STOR_PTR'] - fsm['MRS_STOR_PTR']
                    return fsm
        return None

    SelectAllPDA = 0x7F  # persistent value (latest MRS storage value)
    fsm_SelectAllPDA = None
    
    for fsm_pos, val in enumerate(fsm_list):
        if fsm_pos > 4 and val == 0:
            break  # the end
        fsm = FSM_decode(val)
        if not fsm['ACTIVE']:
            continue
        if fsm['COMMAND_TYPE'] != GmfCmdMpc:
            continue
        #if fsm['ADDRESS'] not in [ 0, 15 ]:
        #    continue
        mrs_pos = fsm["MRS_STOR_PTR"]
        if mrs_pos > 0 and mrs_pos < len(mrs_list):
            mrs_val = mrs_list[mrs_pos]
            if mrs_val == SelectAllPDA:
                fsm_SelectAllPDA = fsm
                fsm_len = fsm_pos + 1
                mrs_size = mrs_pos + 1
                break
    
    if not mrs_size:
        mrs_size = len(mrs_list)
        fsm_len = len(fsm_list)

    mrs_hex_list = [ '%02X' % mrs_list[i] for i in range(0, mrs_size) ]
    tm['mrs_data'] = ' '.join(mrs_hex_list)
    tm['mrs_size'] = mrs_size

    fsm_hex_list = [ '%08X' % fsm_list[i] for i in range(0, fsm_len) ]
    tm['fsm_data'] = ' '.join(fsm_hex_list)
    tm['fsm_len'] = fsm_len
    
    mr = tm['MRS'] = { }
    if not fsm_SelectAllPDA:
        return  # unsupported format
    if mrs_size <= 0:
        return  # MRS not inited
    if mrs_size < 16:
        return  # unsupported format

    MR34 = find_MR_into_FSM(34)
    MR35 = find_MR_into_FSM(35)
    if MR34 and MR35:
        mr['MR34_offset'] = MR34['MRS_STOR_PTR']
        size = MR34['size']
        if size and size > 0:
            mr["RttWr"] = [ ]
            mr["RttPark"] = [ ]
            mr["RttNomWr"] = [ ]
            mr["RttNomRd"] = [ ]
            for k in range(0, size):
                mr["RttWr"].append   ( OdtDecode(get_bits(mrs_data, MR34['MRS_STOR_PTR'] + k, 3, 5)) )
                mr["RttPark"].append ( OdtDecode(get_bits(mrs_data, MR34['MRS_STOR_PTR'] + k, 0, 2)) )
                mr["RttNomWr"].append( OdtDecode(get_bits(mrs_data, MR35['MRS_STOR_PTR'] + k, 0, 2)) )
                mr["RttNomRd"].append( OdtDecode(get_bits(mrs_data, MR35['MRS_STOR_PTR'] + k, 3, 5)) )

    MR36 = find_MR_into_FSM(36)
    if MR36:
        mr["RttLoopback"] = OdtDecode(get_bits(mrs_data, MR36['MRS_STOR_PTR'], 0, 2))
    
    MR13 = find_MR_into_FSM(13)
    if MR13:
        mr['mr13'] = DDR5_MR13_decode(mrs_list[ MR13['MRS_STOR_PTR'] ])
    
    DDR5_MPC_SET_2N_COMMAND_TIMING   = 0x08
    DDR5_MPC_SET_1N_COMMAND_TIMING   = 0x09
    
    DDR5_MPC_RTT_MASK = 0x07
    DDR5_MPC_GROUP_A_RTT_CK   = 0x20
    DDR5_MPC_GROUP_B_RTT_CK   = 0x28
    DDR5_MPC_GROUP_A_RTT_CS   = 0x30
    DDR5_MPC_GROUP_B_RTT_CS   = 0x38
    DDR5_MPC_GROUP_A_RTT_CA   = 0x40
    DDR5_MPC_GROUP_B_RTT_CA   = 0x48
    DDR5_MPC_SET_DQS_RTT_PARK = 0x50
    DDR5_MPC_SET_RTT_PARK     = 0x58
    DDR5_MPC_CFG_TDLLK_TCCD_L = 0x80  # Mask = 0x0F
    
    def rttCx_check_and_read(start, pattern):
        nonlocal mrs_data, mrs_list
        plen = len(pattern)
        vcount = 0
        res = { }
        mrs = [ mrs_list[pos] for pos in range(start, start + plen + 1) ]
        if len(pattern) >= len(mrs):
            return 0, res
        for pi, vname in enumerate(pattern):
            value = mrs[pi]
            vtype = vname
            name = vname
            if '=' in vname:
                vtype, name = vname.split('=')
            idx = None
            if '#' in name:
                name, idx = name.split('#')
                idx = int(idx)
            val = '_SKIP_'
            if vtype == '?':
                vcount += 1
                continue
            if vtype == 'mpcMR13' and (value & 0xF0) == DDR5_MPC_CFG_TDLLK_TCCD_L:
                val = DDR5_MR13_decode(value)
            if vtype == 'mpcSetCmdTiming':
                val = ''
                if value == DDR5_MPC_SET_2N_COMMAND_TIMING:
                    val = '2N'
                if value == DDR5_MPC_SET_1N_COMMAND_TIMING:
                    val = '1N'
            if vtype == 'CKa' and (value & ~DDR5_MPC_RTT_MASK) == DDR5_MPC_GROUP_A_RTT_CK:
                val = CccOdtDecode(value & DDR5_MPC_RTT_MASK)
            if vtype == 'CKb' and (value & ~DDR5_MPC_RTT_MASK) == DDR5_MPC_GROUP_B_RTT_CK:
                val = CccOdtDecode(value & DDR5_MPC_RTT_MASK)
            if vtype == 'CSa' and (value & ~DDR5_MPC_RTT_MASK) == DDR5_MPC_GROUP_A_RTT_CS:
                val = CccOdtDecode(value & DDR5_MPC_RTT_MASK)
            if vtype == 'CSb' and (value & ~DDR5_MPC_RTT_MASK) == DDR5_MPC_GROUP_B_RTT_CS:
                val = CccOdtDecode(value & DDR5_MPC_RTT_MASK)
            if vtype == 'CAa' and (value & ~DDR5_MPC_RTT_MASK) == DDR5_MPC_GROUP_A_RTT_CA:
                val = CccOdtDecode(value & DDR5_MPC_RTT_MASK)
            if vtype == 'CAb' and (value & ~DDR5_MPC_RTT_MASK) == DDR5_MPC_GROUP_B_RTT_CA:
                val = CccOdtDecode(value & DDR5_MPC_RTT_MASK)
            if vtype == 'ParkDqs' and (value & ~DDR5_MPC_RTT_MASK) == DDR5_MPC_SET_DQS_RTT_PARK:
                val = OdtDecode(value & DDR5_MPC_RTT_MASK)
            if vtype == 'Park' and (value & ~DDR5_MPC_RTT_MASK) == DDR5_MPC_SET_RTT_PARK:
                val = OdtDecode(value & DDR5_MPC_RTT_MASK)
            if vtype in [ 'MR0', 'MR2', 'MR4', 'MR5', 'MR6', 'MR8', 'MR10', 'MR11', 'MR12', 'MR13', 'MR14', 'MR32', 'MR33' ]:
                decode_func = globals()[f'DDR5_{vtype}_decode']
                val = decode_func(value)
            if val != '_SKIP_':
                vcount += 1
                if idx is not None:
                    if name not in res:
                        res[name] = [ ]
                    while True:
                        if idx >= len(res[name]):
                            res[name].append(None)
                        else:
                            break
                    res[name][idx] = val
                else:    
                    res[name] = val
        return vcount, res
    
    pattern_Cx_dict = {
        'i12_1x': [
            'mpcMR13=MR13',                      # mpcMR13
            'mpcSetCmdTiming=CmdTiming',         # mpcSetCmdTiming
            'CKa=RttCK_A',                       # mpcMR32a0
            'CSa=RttCS_A',                       # mpcMR32a1
            'CAa=RttCA_A',                       # mpcMR33a0
            'CKb=RttCK_B',                       # mpcMR32b0
            'CSb=RttCS_B',                       # mpcMR32b1
            'CAb=RttCA_B',                       # mpcMR33b0
            '?',
            '?',
            'ParkDqs=RttParkDqs',                # mpcMR33
            'Park=RttPARK',                      # mpcMR34
        ],
        'i12_2x': [
            'mpcMR13=MR13',                      # mpcMR13
            'mpcSetCmdTiming=CmdTiming',         # mpcSetCmdTiming
            'CKa=RttCK_A#0', 'CKa=RttCK_A#1',    # mpcMR32a0
            'CSa=RttCS_A#0', 'CSa=RttCS_A#1',    # mpcMR32a1
            'CAa=RttCA_A#0', 'CAa=RttCA_A#1',    # mpcMR33a0
            'CKb=RttCK_B#0', 'CKb=RttCK_B#1',    # mpcMR32b0
            'CSb=RttCS_B#0', 'CSb=RttCS_B#1',    # mpcMR32b1
            'CAb=RttCA_B#0', 'CAb=RttCA_B#1',    # mpcMR33b0
            '?', '?',                            # MR11
            '?', '?',                            # MR12
            'ParkDqs=RttParkDqs#0', 'ParkDqs=RttParkDqs#1',   # mpcMR33
            'Park=RttPARK#0', 'Park=RttPARK#1',               # mpcMR34
        ],
        'i12_4x': [
            'mpcMR13=MR13',                      # mpcMR13
            'mpcSetCmdTiming=CmdTiming',         # mpcSetCmdTiming
            'CKa=RttCK_A#0', 'CKa=RttCK_A#1', 'CKa=RttCK_A#2', 'CKa=RttCK_A#3',
            'CSa=RttCS_A#0', 'CSa=RttCS_A#1', 'CSa=RttCS_A#2', 'CSa=RttCS_A#3',
            'CAa=RttCA_A#0', 'CAa=RttCA_A#1', 'CAa=RttCA_A#2', 'CAa=RttCA_A#3',
            'CKb=RttCK_B#0', 'CKb=RttCK_B#1', 'CKb=RttCK_B#2', 'CKb=RttCK_B#3',
            'CSb=RttCS_B#0', 'CSb=RttCS_B#1', 'CSb=RttCS_B#2', 'CSb=RttCS_B#3',
            'CAb=RttCA_B#0', 'CAb=RttCA_B#1', 'CAb=RttCA_B#2', 'CAb=RttCA_B#3',
            '?', '?', '?', '?',
            '?', '?', '?', '?',
            'ParkDqs=RttParkDqs#0', 'ParkDqs=RttParkDqs#1', 'ParkDqs=RttParkDqs#2', 'ParkDqs=RttParkDqs#3',
            'Park=RttPARK#0', 'Park=RttPARK#1', 'Park=RttPARK#2', 'Park=RttPARK#3',
        ],
        'i15': [
            'mpcMR13=MR13#0', 'mpcMR13=MR13#1',  # mpcMR13
            'mpcSetCmdTiming=CmdTiming',         # mpcSetCmdTiming
            'CKa=RttCK_A',                       # mpcMR32a0
            'CSa=RttCS_A',                       # mpcMR32a1
            'CAa=RttCA_A',                       # mpcMR33a0
            'CKb=RttCK_B',                       # mpcMR32b0
            'CSb=RttCS_B',                       # mpcMR32b1
            'CAb=RttCA_B',                       # mpcMR33b0
            '?',
            '?',
            'ParkDqs=RttParkDqs',                # mpcMR33
            'Park=RttPARK',                      # mpcMR34
        ],
    }
    for pname in pattern_Cx_dict:
        if cpu_id in i12_FAM and not pname.startswith('i12') :
            pattern_Cx_dict[pname] = None
        if cpu_id in i15_FAM and not pname.startswith('i15') :
            pattern_Cx_dict[pname] = None

    rttCx_start = 0
    rttCx_size = 0
    rttCx_pattern = ''
    rttCx = None
    for pname, pattern in pattern_Cx_dict.items():
        if not pattern:
            continue
        sz, res = rttCx_check_and_read(rttCx_start, pattern)
        if sz == len(pattern):
            rttCx = res
            rttCx_size = len(pattern) 
            rttCx_pattern = pname
            break
    if rttCx:
        mr.update( rttCx )

    MR11 = find_MR_into_FSM(11, GmfCmdVref)
    if MR11 and MR11['size'] and MR11['size'] > 0:
        mr["VrefCA"] = [ ]
        for k in range(0, MR11['size']):
            mr["VrefCA"].append( DDR5_MR11_decode(mrs_list[ MR11['MRS_STOR_PTR'] + k ]) )

    MR12 = find_MR_into_FSM(12, GmfCmdVref)
    if MR12 and MR12['size'] and MR12['size'] > 0:
        mr["VrefCS"] = [ ]
        for k in range(0, MR12['size']):
            mr["VrefCS"].append( DDR5_MR12_decode(mrs_list[ MR12['MRS_STOR_PTR'] + k ]) )
    
    MR10 = find_MR_into_FSM(10)
    if MR10 and MR10['size'] and MR10['size'] > 0:
        mr["VrefDQ"] = [ ]
        for k in range(0, MR10['size']):
            mr["VrefDQ"].append( DDR5_MR10_decode(mrs_list[ MR10['MRS_STOR_PTR'] + k ]) )

    for mr_num in [ 0, 2, 4, 5, 6, 8, 14 ]:
        fsm = find_MR_into_FSM(mr_num)
        if fsm:
            value = mrs_list[ fsm['MRS_STOR_PTR'] ]
            decode_func = globals()[f'DDR5_MR{mr_num}_decode']
            val = decode_func(value)
            mr[f'MR{mr_num}'] = val

    for key, val in mr.items():
        if isinstance(val, list) and len(val) == 1:
            mr[key] = val[0]

    mr["SelectAllPDA"] = mrs_list[ fsm_SelectAllPDA['MRS_STOR_PTR'] ]

def get_mem_ctrl(ctrl_num):
    global gdict, gcpuinfo, cpu_id, MCHBAR_BASE
   
    mi = { }
    mi['controller'] = ctrl_num
   
    MC_REGS_SIZE = None
    MCHBAR_addr = MCHBAR_BASE + (0x10000 * ctrl_num)
    if cpu_id in i12_FAM or cpu_id in i15_FAM:
        MC_REGS_SIZE = 0x800
        data_offset = 0xD800  # Inter-Channel Decode Parameters
        MADCH = phymem_read(MCHBAR_addr + data_offset, 4)
        mi["DDR_TYPE"]     = get_bits(MADCH, 0, 0, 2)
        mi["CH_L_MAP"]     = get_bits(MADCH, 0, 4, 4)  # Channel L mapping to physical channel.  0 = Channel 0  1 = Channel 1
        mi["CH_S_SIZE"]    = get_bits(MADCH, 0, 12, 19)
        mi["CH_WIDTH"]     = get_bits(MADCH, 0, 27, 28)
        mi["HALFCACHELINEMODE"] = get_bits(MADCH, 0, 31, 31)   # HALF_CL_MODE
        if mi["DDR_TYPE"] in [ DDR_TYPE.DDR4, DDR_TYPE.LPDDR4 ]:
            mi["DDR_ver"] = 4
        elif mi["DDR_TYPE"] in [ DDR_TYPE.DDR5, DDR_TYPE.LPDDR5 ]:
            mi["DDR_ver"] = 5
        else:
            raise RuntimeError()
        mi['DDR_type'] = DDR_TYPE(mi["DDR_TYPE"]).name
    else:
        raise RuntimeError(f'ERROR: Processor model 0x{cpu_id:X} not supported')
    #print(json.dumps(mi, indent = 4))
    mchan = [ ]
    # 0xD804 - Intra-Channel 0 Decode Parameters
    # 0xD808 - Intra-Channel 1 Decode Parameters
    # 0xD80C - Channel 0 DIMM Characteristics
    # 0xD810 - Channel 1 DIMM Characteristics
    for cnum in range(0, 2):
        mc = { }
        mc["__channel"] = cnum
        data = phymem_read(MCHBAR_addr + 0xD804 + cnum * 4, 4)
        if data == b'\xFF\xFF\xFF\xFF':
            raise RuntimeError()
        mc["DIMM_L_MAP"] = get_bits(data, 0, 0, 0)  # Virtual DIMM L mapping to physical DIMM: 0 = DIMM0, 1 = DIMM1
        mc["EIM"] = get_bits(data, 0, 8, 8)
        mc["ECC"] = get_bits(data, 0, 12, 13)
        if cpu_id in i12_FAM:
            mc["CRC"] = get_bits(data, 0, 14, 14)   # CRC Mode: 0 = Disabled  1 = Enabled
        data = phymem_read(MCHBAR_addr + 0xD80C + cnum * 4, 4)
        if data == b'\xFF\xFF\xFF\xFF':
            raise RuntimeError()
        mc["Dimm_L_Size"] = get_bits(data, 0, 0, 6)   # DIMM L Size in 512 MB multiples
        if cpu_id in i12_FAM:
            mc["DLW"]         = get_bits(data, 0, 7, 8)   # DIMM L width: 0=x8, 1=x16, 2=x32 
            mc["DLNOR"]       = get_bits(data, 0, 9, 10)  # DIMM L ranks: 0=1, 1=2, 2=3, 3=4
        if cpu_id in i15_FAM:
            mc["DLW"]         = get_bits(data, 0, 7)      # DIMM L width: 0=x8, 1=x16
            mc["DLNOR"]       = get_bits(data, 0, 9)      # DIMM L ranks: 0=1, 1=2
        if cpu_id in i12_FAM:
            mc["DDR5_DS_8GB"] = get_bits(data, 0, 11, 11) # DIMM S: 1 = 8Gb , 0 = more than 8Gb capacity
            mc["DDR5_DL_8GB"] = get_bits(data, 0, 12, 12) # DIMM L: 0 = DDR5 capacity is more than 8Gb, 1 = DDR5 capacity is 8Gb
        mc["Dimm_S_Size"] = get_bits(data, 0, 16, 22)
        if cpu_id in i12_FAM:
            mc["DSW"]         = get_bits(data, 0, 24, 25) # DIMM S width: 0=x8, 1=x16, 2=x32
            mc["DSNOR"]       = get_bits(data, 0, 26, 27) # DIMM S ranks: 0=1, 1=2, 2=3, 3=4
        if cpu_id in i15_FAM:
            mc["DSW"]         = get_bits(data, 0, 24)     # DIMM S width: 0=x8, 1=x16
            mc["DSNOR"]       = get_bits(data, 0, 26)     # DIMM S ranks: 0=1, 1=2
        if cpu_id in i12_FAM:    
            mc["BG0_BIT_OPTIONS"] = get_bits(data, 0, 28, 29)
            mc["DECODER_EBH"] = get_bits(data, 0, 30, 31)
        mchan.append( mc )
    #if mi["CH_L_MAP"]:
    #    mchan.reverse()
    mi['channels'] = mchan
    for channel in range(0, 2):    
        mchan[channel]['info'] = get_mchbar_info(mi, ctrl_num, channel)
    return mi

def get_mem_capabilities():
    global gdict, cpu_id
    gdict['CAP'] = { }
    cap = gdict['CAP']

    CAP_A = pci_cfg_read(0, 0, 0, 0xE4, 4)  # Capabilities A. Processor capability enumeration.
    cap['NVME_F7D'] = get_bits(CAP_A, 0, 1, 1)
    cap['DDR_OVERCLOCK'] = get_bits(CAP_A, 0, 3, 3)
    cap['CRID'] = get_bits(CAP_A, 0, 4, 7)
    cap['2LM_SUPPORTED'] = get_bits(CAP_A, 0, 8, 8)
    cap['DID0OE'] = get_bits(CAP_A, 0, 10, 10)
    cap['IntGpu'] = True if get_bits(CAP_A, 0, 11, 11) == 0 else False     # IGD: Internal Graphics Status
    cap['DualMemChan'] = True if get_bits(CAP_A, 0, 12, 12) == 0 else False  # PDCD: Dual Memory Channel Support
    cap['X2APIC_EN'] = get_bits(CAP_A, 0, 13, 13)
    cap['TwoDimmPerChan'] = True if get_bits(CAP_A, 0, 14, 14) == 0 else False   # DDPCD: 2 DIMMs Per Channel Status
    cap['DTT_dev'] = True if get_bits(CAP_A, 0, 15, 15) == 0 else False     # CDD: DTT Device Status
    cap['D1NM'] = True if get_bits(CAP_A, 0, 17, 17) == 0 else False       # DRAM 1N Timing Status
    cap['PEG60'] = True if get_bits(CAP_A, 0, 18, 18) == 0 else False      # PEG60D: PCIe Controller Device 6 Function 0 Status
    cap['DDRSZ'] = get_bits(CAP_A, 0, 19, 20)  # DRAM Maximum Size per Channel
    DRAM_SIZE_map = { 0: None, 1: '8GB', 2: '4GB', 3: '2GB' }
    cap['DDRSZ_max'] = DRAM_SIZE_map[cap['DDRSZ']]
    if cpu_id in i12_FAM:
        cap['DMIG2'] = True if get_bits(CAP_A, 0, 22, 22) == 0 else False  # DMIG2DIS: DMI GEN2 Status
    cap['VTD'] = True if get_bits(CAP_A, 0, 23, 23) == 0 else False  # VTDD:  VT-d status
    cap['FDEE'] = get_bits(CAP_A, 0, 24, 24)  # Force DRAM ECC Enable
    cap['ECC'] = True if get_bits(CAP_A, 0, 25, 25) == 0 else False  # ECCDIS : DRAM ECC status
    if cpu_id in i12_FAM:
        cap['DW'] = 'x4' if get_bits(CAP_A, 0, 26, 26) == 0 else 'x2'   # DMI Width
    cap['PELWU'] = True if get_bits(CAP_A, 0, 27, 27) == 0 else False  # PELWUD : PCIe Link Width Up-config
    CAP_B = pci_cfg_read(0, 0, 0, 0xE8, 4)  # Capabilities B. Processor capability enumeration.
    cap['SPEGFX1'] = get_bits(CAP_B, 0, 0)    
    cap['DPEGFX1'] = get_bits(CAP_B, 0, 1)    
    cap['VMD'] = True if get_bits(CAP_B, 0, 2) == 0 else False    # VMD_DIS
    cap['SH_OPI_EN'] = get_bits(CAP_B, 0, 3)    
    cap['Debug'] = True if get_bits(CAP_B, 0, 7) == 0 else False   # Debug mode status
    cap['GNA'] = True if get_bits(CAP_B, 0, 8) == 0 else False     # GNA_DIS
    cap['DEV10'] = True if get_bits(CAP_B, 0, 10) == 0 else False    # DEV10_DISABLED
    cap['HDCP'] = True if get_bits(CAP_B, 0, 11) == 0 else False     # HDCPD
    cap['LTECH'] = get_bits(CAP_B, 0, 12, 14)    
    if cpu_id in i12_FAM:
        cap['DMIG3'] = True if get_bits(CAP_B, 0, 15) == 0 else False   # DMIG3DIS 
        cap['PEGX16'] = True if get_bits(CAP_B, 0, 16) == 0 else False    # PEGX16D
    if cpu_id in i15_FAM:
        cap['CDIE'] = True if get_bits(CAP_B, 0, 17) == 0 else False    # CDIE_?DISABLE
    cap['PKGTYP'] = get_bits(CAP_B, 0, 19)    
    if cpu_id in i12_FAM:
        cap['PEGG3'] = True if get_bits(CAP_B, 0, 20) == 0 else False    # PEGG3_DIS
    cap['PLL_REF100_CFG'] = get_bits(CAP_B, 0, 21, 23)  # DDR Maximum Frequency Capability with 100MHz memory reference clock (ref_clk). 0: 100 MHz memory reference clock is not supported / 1-6: Reserved / 7: Unlimited
    cap['SVM'] = True if get_bits(CAP_B, 0, 24) == 0 else False  # SVM_DISABLE  
    cap['CACHESZ'] = get_bits(CAP_B, 0, 25, 27)    
    cap['SMT'] = get_bits(CAP_B, 0, 28)    
    cap['OC_ENABLED'] = get_bits(CAP_B, 0, 29)   # Overclocking Enabled 
    cap['TRACE_HUB'] = True if get_bits(CAP_B, 0, 30) == 0 else False   # TRACE_HUB_DIS 
    cap['IPU'] = True if get_bits(CAP_B, 0, 31) == 0 else False   # IPU_DIS  
    CAP_C = pci_cfg_read(0, 0, 0, 0xEC, 4)  # Capabilities C. Processor capability enumeration.
    cap['DISPLAY_PIPE3'] = get_bits(CAP_C, 0, 5)
    cap['IDD'] = get_bits(CAP_C, 0, 6)
    cap['BCLKOCRANGE'] = get_bits(CAP_C, 0, 7, 8)  # BCLK Overclocking maximum frequency
    BCLK_OC_map = { 0: 'disabled', 1: 'max=115MHz', 2: 'max=130MHz', 3: 'unlimited' }
    cap['BCLKOC_freq_limit'] = BCLK_OC_map[cap['BCLKOCRANGE']]
    cap['QCLK_GV'] = True if get_bits(CAP_C, 0, 14) == 0 else False   # QCLK_GV_DIS
    if cpu_id in i15_FAM:
        cap['VPU'] = True if get_bits(CAP_C, 0, 15) == 0 else False   # VPU_?DIS
    cap['LPDDR4_EN'] = get_bits(CAP_C, 0, 16)
    cap['MAX_DATA_RATE_LPDDR4'] = get_bits(CAP_C, 0, 17, 21)
    cap['DDR4_EN'] = get_bits(CAP_C, 0, 22)
    cap['MAX_DATA_RATE_DDR4'] = get_bits(CAP_C, 0, 23, 27)
    if cpu_id in i12_FAM:
        cap['PEGG4'] = True if get_bits(CAP_C, 0, 28) == 0 else False   # PEGG4_DIS
        cap['PEGG5'] = True if get_bits(CAP_C, 0, 29) == 0 else False   # PEGG5_DIS
        cap['PEG61'] = True if get_bits(CAP_C, 0, 30) == 0 else False   # PEG61D
    CAP_E = pci_cfg_read(0, 0, 0, 0xF0, 4)  # Capabilities E. Processor capability enumeration.
    cap['LPDDR5_EN'] = get_bits(CAP_E, 0, 0)
    if cpu_id in i12_FAM:
        cap['MAX_DATA_RATE_LPDDR5'] = get_bits(CAP_E, 0, 1, 5)
        cap['MAX_DATA_FREQ_LPDDR5'] = None
        cap['DDR5_EN'] = get_bits(CAP_E, 0, 6)
        cap['MAX_DATA_RATE_DDR5'] = get_bits(CAP_E, 0, 7, 11)
        cap['MAX_DATA_FREQ_DDR5'] = None
        cap['IBECC'] = True if get_bits(CAP_E, 0, 12) == 0 else False  # IBECC_DIS
        VDDQ_VOLTAGE_MAX = get_bits(CAP_E, 0, 13, 23)
    if cpu_id in i15_FAM:
        cap['MAX_DATA_RATE_LPDDR5'] = get_bits(CAP_E, 0, 1, 8)
        cap['MAX_DATA_FREQ_LPDDR5'] = None
        cap['DDR5_EN'] = get_bits(CAP_E, 0, 9)
        cap['MAX_DATA_RATE_DDR5'] = get_bits(CAP_E, 0, 10, 17)
        cap['MAX_DATA_FREQ_DDR5'] = None
        cap['IBECC'] = True if get_bits(CAP_E, 0, 18) == 0 else False  # IBECC_DIS
        VDDQ_VOLTAGE_MAX = get_bits(CAP_E, 0, 19, 29)
    cap['MAX_DATA_FREQ_LPDDR5'] = cap['MAX_DATA_RATE_LPDDR5'] * 266
    cap['MAX_DATA_FREQ_DDR5'] = cap['MAX_DATA_RATE_DDR5'] * 266
    cap['VDDQ_VOLTAGE_MAX'] = round(VDDQ_VOLTAGE_MAX * 5 / 1000, 3)  # VDDQ_TX Maximum VID value (granularity UNDOC !!!)

def get_mem_info(with_msr = True, with_bios = True):
    global gdict, gcpuinfo, cpu_id, MCHBAR_BASE, DMIBAR_BASE
    gcpuinfo = get_cpu_info(log = True)
    cpu_id = get_cpu_id()

    if gcpuinfo['family'] != 6:
        raise RuntimeError(f'ERROR: Currently support only Intel processors')

    if cpu_id < CPUID.ALDERLAKE:
        raise RuntimeError(f'ERROR: Processor model 0x{cpu_id:X} not supported')

    MCHBAR_BASE = pci_cfg_read(0, 0, 0, 0x48, '8')
    if (MCHBAR_BASE & 1) != 1:
        raise RuntimeError(f'ERROR: Readed incorrect MCHBAR_BASE = 0x{MCHBAR_BASE:X}')
    if MCHBAR_BASE < 0xFE000000 or MCHBAR_BASE >= 0xFFFFFFFF - 0x10000 * 3:
        raise RuntimeError(f'ERROR: Readed incorrect MCHBAR_BASE = 0x{MCHBAR_BASE:X}')
    MCHBAR_BASE = MCHBAR_BASE - 1
    print(f'MCHBAR_BASE = 0x{MCHBAR_BASE:X}')

    dmibar_addr = pci_cfg_read(0, 0, 0, 0x68, '8')
    DMIBAR_EN = get_bits(dmibar_addr, 0, 0, 1)
    if not DMIBAR_EN:
        print(f'DMIBAR_EN = False (0x{dmibar_addr:08X})')
    else:
        DMIBAR_addr = get_bits(dmibar_addr, 0, 12, 41)
        DMIBAR_BASE = DMIBAR_addr << 12
        print(f'DMIBAR_BASE = 0x{DMIBAR_BASE:X}')
        DMI_DeviceId = phymem_read(DMIBAR_BASE, 4)
        DMI_VID = get_bits(DMI_DeviceId, 0, 0, 15)
        DMI_DID = get_bits(DMI_DeviceId, 0, 16, 31)
        print(f'DMI_VID = 0x{DMI_VID:X}  DMI_DID = 0x{DMI_DID:X}')
        if DMI_VID != PCI_VENDOR_ID_INTEL:
            raise RuntimeError(f'ERROR: Currently support only Intel processors')

    #mchbar_mmio = MCHBAR_BASE + 0x6000

    gdict = { }
    gdict['cpu'] = gcpuinfo.copy()
    board = gdict['board'] = { }
    R_SA_MC_DEVICE_ID = 0x02
    gdict['cpu']['DeviceID'] = pci_cfg_read(0, 0, 0, R_SA_MC_DEVICE_ID, '2')

    get_mem_capabilities()

    if g_fake_cpu_id:
        cpu_id = g_fake_cpu_id
        gdict['cpu']['model_id'] = cpu_id

    if with_msr:
        import msrbox
        mmb = msrbox.MsrMailBox()
        mmb.cpu_id = cpu_id
        gdict['MSR'] = mmb.read_full_info()

    if with_bios:
        import biosbox
        bmb = biosbox.BiosMailBox()
        bmb.cpu_id = cpu_id
        gdict['BIOS'] = bmb.read_full_info()

    gdict['memory'] = { }
    mi = gdict['memory']

    data = phymem_read(MCHBAR_BASE + 0x5F58, 8)
    mi['MC_TIMING_RUNTIME_OC_ENABLED'] = get_bits(data, 0, 0, 0)  # Adjusting memory timing values for overclocking is enabled
    data = phymem_read(MCHBAR_BASE + 0x5F60, 8)
    BCLK_FREQ = get_bits(data, 0, 0, 31) / 1000.0  # Reported BCLK Frequency in KHz
    mi['BCLK_FREQ'] = round(BCLK_FREQ, 3)
    if cpu_id in i15_FAM:
        mi['SOCBCLK_FREQ'] = mi['BCLK_FREQ']
        CPUBCLK_FREQ = get_bits(data, 0, 32, 63) / 1000.0  # Reported PCIE BCLK Frequency in Khz
        mi['CPUBCLK_FREQ'] = round(CPUBCLK_FREQ, 3)

    pw = mi['POWER'] = { }
    if cpu_id in i12_FAM:
        data = phymem_read(MCHBAR_BASE + 0x58E0, 8)   # DDR Power Limit
        pw['LIMIT1_POWER'] = get_bits(data, 0, 0, 14) * 0.125   # Power Limit 1 (PL1) for DDR domain in Watts. Format is U11.3: Resolution 0.125W, Range 0-2047.875W
        pw['LIMIT1_ENABLE'] = get_bits(data, 0, 15, 15)         # Power Limit 1 (PL1) enable bit for DDR domain
        pw['LIMIT1_TIME_WINDOW_Y'] = get_bits(data, 0, 17, 21)  # Power Limit 1 (PL1) time window Y value, for DDR domain. Actual time window for RAPL is: (1/1024 seconds) * (1+(X/4)) * (2Y)
        pw['LIMIT1_TIME_WINDOW_X'] = get_bits(data, 0, 22, 23)  # Power Limit 1 (PL1) time window X value, for DDR domain. Actual time window for RAPL is: (1/1024 seconds) * (1+(X/4)) * (2Y) 
        pw['LIMIT2_POWER'] = get_bits(data, 0, 32, 46) * 0.125  # Power Limit 2 (PL2) for DDR domain in Watts. Format is U11.3: Resolution 0.125W, Range 0-2047.875W.
        pw['LIMIT2_ENABLE'] = get_bits(data, 0, 47, 47)         # Power Limit 2 (PL2) enable bit for DDR domain.
        pw['limits_LOCKED'] = get_bits(data, 0, 63, 63)  # When set, this entire register becomes read-only. This bit will typically be set by BIOS during boot.
    data = phymem_read(MCHBAR_BASE + 0x58F0, 4)   # Package RAPL Performance Status
    pw['RAPL_COUNTS'] = get_bits(data, 0, 0, 31)
    if cpu_id in i12_FAM:
        data = phymem_read(MCHBAR_BASE + 0x5920, 4)   # Primary Plane Turbo Policy
        pw['PRIPTP'] = get_bits(data, 0, 0, 4)  # Priority Level. A higher number implies a higher priority.
    if cpu_id in i15_FAM:
        data = phymem_read(MCHBAR_BASE + 0x5920, 4)   # GT IA Performance BIAS
        pw['IA_PERF_MULTIPLIER'] = get_bits(data, 0, 0, 15)   # IA Performance Multiplier, in U1.15 format
        pw['GT_PERF_MULTIPLIER'] = get_bits(data, 0, 16, 31)  # GT Performance Multiplier, in U1.15 format
    data = phymem_read(MCHBAR_BASE + 0x5924, 4)   # Secondary Plane Turbo Policy
    pw['SECPTP'] = get_bits(data, 0, 0, 4)  # Priority Level. A higher number implies a higher priority.
    data = phymem_read(MCHBAR_BASE + 0x5928, 4)   # Primary Plane Energy Status
    pw['PRI_P_DATA'] = get_bits(data, 0, 0, 31)   # Energy Value. The value of this register is updated every 1mSec.
    data = phymem_read(MCHBAR_BASE + 0x592C, 4)   # Primary Plane Energy Status
    pw['SEC_P_DATA'] = get_bits(data, 0, 0, 31)   # Energy Value. The value of this register is updated every 1mSec.
    data = phymem_read(MCHBAR_BASE + 0x5938, 4)   # Package Power SKU Unit
    pw['PWR_UNIT'] = get_bits(data, 0, 0, 3)  # Power Units used for power control registers. The actual unit value is calculated by 1 W / Power(2, PWR_UNIT). The default value of 0011b corresponds to 1/8 W.
    pw['ENERGY_UNIT'] = get_bits(data, 0, 8, 12)
    pw['TIME_UNIT'] = get_bits(data, 0, 16, 19)
    data = phymem_read(MCHBAR_BASE + 0x593C, 4)   # Package Energy Status
    pw['PKG_ENG_STATUS'] = get_bits(data, 0, 0, 31)  # Package energy consumed by the entire CPU (including IA, GT and uncore). The counter will wrap around and continue counting when it reaches its limit.
    data = phymem_read(MCHBAR_BASE + 0x597C, 4)   # Package Energy Status
    pw['PP0_Temperature'] = get_bits(data, 0, 0, 7)  # PP0 (IA Cores) temperature in degrees (C).

    sa = mi['SA'] = { }
    data = phymem_read(MCHBAR_BASE + 0x5918, 8)   # System Agent Performance Status
    sa['LAST_DE_WP_REQ_SERVED'] = get_bits(data, 0, 0, 1)   # Last display engine workpoint request served by the PCU
    sa['QCLK_REFERENCE'] = get_bits(data, 0, 10, 10)  # 0 = 133.34Mhz  1 = 100 MHz
    QCLK_REF_FREQ = 100.0 if sa['QCLK_REFERENCE'] else 133.34  # MHz
    sa['QCLK_REF_FREQ'] = QCLK_REF_FREQ
    sa['QCLK_RATIO'] = get_bits(data, 0, 2, 9)  # Reference clock is determined by the QCLK_REFERENCE field.
    sa['QCLK_FREQ'] = round(sa['QCLK_RATIO'] * mi['BCLK_FREQ'], 3)
    if sa['QCLK_REFERENCE'] == 0 and mi['BCLK_FREQ'] < 126:
        sa['QCLK_FREQ'] = round(sa['QCLK_RATIO'] * 133.34, 3)
    sa['OPI_LINK_SPEED'] = get_bits(data, 0, 11, 11)  # 0: 2Gb/s    1: 4Gb/s
    sa['IPU_IS_DIVISOR'] = get_bits(data, 0, 12, 17)  # The frequency is 1600MHz/Divisor 
    sa['IPU_IS_freq'] = 1600 / sa['IPU_IS_DIVISOR'] if sa['IPU_IS_DIVISOR'] > 0 else None
    sa['IPU_PS_RATIO'] = get_bits(data, 0, 18, 23)  # IPU PS RATIO. The frequency is 25MHz * Ratio.
    sa['IPU_PS_freq'] = 25.0 * sa['IPU_PS_RATIO']
    sa['UCLK_RATIO'] = get_bits(data, 0, 24, 31)  # Used to calculate the ring's frequency. Ring Frequency = UCLK_RATIO * BCLK
    sa['UCLK'] = round(sa['UCLK_RATIO'] * mi['BCLK_FREQ'], 3)
    sa['PSF0_RATIO'] = get_bits(data, 0, 32, 39)  # Reports the PSF0 PLL ratio. The PSF0 frequency is: Ratio * 16.67MHz.
    sa['PSF0_freq'] = round(16.67 * sa['PSF0_RATIO'], 3)
    sa['SA_VOLTAGE'] = get_bits(data, 0, 40, 55)  # Reports the System Agent voltage in u3.13 format. Conversion to Volts: V = SA_VOLTAGE / 8192.0
    sa['SA_VOLTAGE'] = round(sa['SA_VOLTAGE'] / 8192, 3)

    if cpu_id in i12_FAM:
        bios = mi['BIOS_REQUEST'] = { }
        data = phymem_read(MCHBAR_BASE + 0x5E00, 4)   # Memory Controller BIOS Request
        MC_PLL_RATIO = get_bits(data, 0, 0, 7) # This field holds the memory controller frequency (QCLK).
        bios['MC_PLL_REF'] = get_bits(data, 0, 8, 11)
        bios['MC_PLL_RATIO'] = MC_PLL_RATIO
        bios['MC_PLL_freq'] = MC_PLL_RATIO * 100.0 if bios['MC_PLL_REF'] == 1 else round(MC_PLL_RATIO * 133.33, 3)
        bios['GEAR'] = 1 << get_bits(data, 0, 12, 13)
        bios['REQ_VDDQ_TX_VOLTAGE'] = round(get_bits(data, 0, 17, 26) * 5 / 1000, 3) # Voltage of the VDDQ TX rail at this clock frequency and gear configuration. Described in 5mV resolution
        bios['REQ_VDDQ_TX_ICCMAX'] = round(get_bits(data, 0, 27, 30) * 0.25, 3)  # Described in 0.25A resolution. IccMax: 32 * 0.25 = 8A
        bios['RUN_BUSY'] = get_bits(data, 0, 31, 31)

        #bios = mi['BIOS_DATA'] = { }
        bios = mi
        data = phymem_read(MCHBAR_BASE + 0x5E04, 4)   # Memory Controller BIOS Data
        MC_PLL_RATIO = get_bits(data, 0, 0, 7) # This field holds the memory controller frequency (QCLK).
        bios['MC_PLL_REF'] = get_bits(data, 0, 8, 11)
        bios['MC_PLL_RATIO'] = MC_PLL_RATIO
        bios['MC_PLL_freq'] = MC_PLL_RATIO * 100.0 if bios['MC_PLL_REF'] == 1 else round(MC_PLL_RATIO * 133.33, 3)
        bios['GEAR'] = 1 << get_bits(data, 0, 12, 13)
        bios['REQ_VDDQ_TX_VOLTAGE'] = round(get_bits(data, 0, 17, 26) * 5 / 1000, 3) # Voltage of the VDDQ TX rail at this clock frequency and gear configuration. Described in 5mV resolution
        bios['REQ_VDDQ_TX_ICCMAX'] = round(get_bits(data, 0, 27, 30) * 0.25, 3)  # Described in 0.25A resolution. IccMax: 32 * 0.25 = 8A

    if cpu_id in i15_FAM:
        bios = mi['BIOS_REQUEST'] = { }
        data = phymem_read(MCHBAR_BASE + 0x13D08, 4)   # MemSS PMA BIOS request register
        bios['QCLK_REF_FREQ'] = 33.334 # MHz
        bios['QCLK_RATIO'] = get_bits(data, 0, 0, 7)
        bios['QCLK_FREQ'] = round(bios['QCLK_RATIO'] * bios['QCLK_REF_FREQ'], 2)
        bios['GEAR'] = 2 if get_bits(data, 0, 8) == 0 else 4
        bios['MAX_BW_MBPS'] = get_bits(data, 0, 9, 28)
        bios['QCLK_WP_IDX'] = get_bits(data, 0, 29, 30)
        bios['RUN_BUSY'] = get_bits(data, 0, 31)

        bios = mi
        data = phymem_read(MCHBAR_BASE + 0x13D10, 4)   # MemSS PMA BIOS data register
        bios['QCLK_REF_FREQ'] = 33.334 # MHz
        bios['QCLK_RATIO'] = get_bits(data, 0, 0, 7)
        bios['QCLK_FREQ'] = round(bios['QCLK_RATIO'] * bios['QCLK_REF_FREQ'], 2)
        bios['GEAR'] = 2 if get_bits(data, 0, 8) == 0 else 4

    if cpu_id in i12_FAM:
        data = phymem_read(MCHBAR_BASE + 0x5F00, 4)   # System Agent Power Management Control
        mi['SACG_ENA'] = get_bits(data, 0, 0, 0)  # This bit is used to enable or disable the System Agent Clock Gating (FCLK) : 0 = Not Allow , 1 = Allow
        mi['MPLL_OFF_ENA'] = get_bits(data, 0, 1, 1)  # This bit is used to enable shutting down the Memory Controller PLLs (MCPLL and GDPLL).   0b: PLL shutdown is not allowed   1b: PLL shutdown is allowed
        mi['PPLL_OFF_ENA'] = get_bits(data, 0, 2, 2)  # This bit is used to enable shutting down the PCIe/DMI PLL
        mi['SACG_SEN'] = get_bits(data, 0, 8, 8)  # This bit indicates when the System Agent clock gating is possible based on link active power states.
        mi['MPLL_OFF_SEN'] = get_bits(data, 0, 9, 9) # This bit indicates when the Memory PLLs (MCPLL and GDPLL) may be shutdown based on link active power states.
        mi['MDLL_OFF_SEN'] = get_bits(data, 0, 10, 10) # This bit indicates when the Memory Master DLL may be shutdown based on link active power states.
        mi['SACG_SREXIT'] = get_bits(data, 0, 11, 11)  # The Display Engine can indicate to the PCU that it wants the Memory Controller to exit self-refresh
        mi['NSWAKE_SREXIT'] = get_bits(data, 0, 12, 12)  # When this bit is set to 1b, a Non-Snoop wakeup signal from the PCH will cause the PCU to force the memory controller to exit from Self-Refresh
        mi['SACG_MPLL'] = get_bits(data, 0, 13, 13)  # When this bit is set to 1b, FCLK will never be gated when the memory controller PLL is ON.
        mi['MPLL_ON_DE'] = get_bits(data, 0, 14, 14)
        mi['MDLL_ON_DE'] = get_bits(data, 0, 15, 15)
    
    # BCLKOCRANGE

    if True:
        mb = get_motherboard_info()
        board['manufacturer'] = mb['manufacturer']
        board['product'] = mb['product']

    mc = gdict['memory']['mc'] = [ ]
    for ctrl_num in range(0, 2):
        mem = get_mem_ctrl(ctrl_num)
        mc.append( mem )
    return gdict

def dump_mchbar(offset, size):
    global MCHBAR_BASE 
    if not MCHBAR_BASE:
        return False
    return phymem_read(MCHBAR_BASE + offset, size)
    
def dump_mchbar_to_file(offset, size, filename = None):
    data = dump_mchbar(offset, size)
    if not data:
        return False
    fn = filename if filename else f'MCHBAR_{offset:04X}.dat' 
    with open(fn, 'wb') as file:
        file.write(data)
    if not filename:
        print(f'File "{fn}" created!')
    return True

if __name__ == "__main__":
    get_cpu_info(log = True)
    dump_raw_mchbar = False
    if len(sys.argv) > 1:
        if sys.argv[1].lower() == 'mchbar':
            dump_raw_mchbar = True
        if sys.argv[1].lower() == 'test':
            fn = sys.argv[2]
            with open(fn, 'rb') as file:
                g_fake_mchbar = file.read()
            g_fake_cpu_id = int(sys.argv[3])
    
    SdkInit(None, 0)
    out = get_mem_info()
    out_fn = 'IMC_mini.json'

    if g_fake_mchbar and os.path.exists('DIMM_fake.json'):
        with open('DIMM_fake.json', 'r', encoding='utf-8') as file:
            dimm = json.load(file)
        out['memory']['DIMM'] = dimm['DIMM']
        out_fn = 'IMC.json'
    
    with open(out_fn, 'w') as file:
        json.dump(out, file, indent = 4)
        print(f'File "{out_fn}" created!')

    if dump_raw_mchbar:
        dump_mchbar_to_file(0, 0x10000 * 3)
