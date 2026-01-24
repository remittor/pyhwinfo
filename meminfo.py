#
# Copyright (C) 2025 remittor
#

import sys
import json
import types
import ctypes
import math

import tkinter as tk
from tkinter import ttk
try:
    from tkextrafont import load_extrafont
except ImportError:
    print('Module "tkextrafont" not found!')
    def load_extrafont(root):
        pass  # Fallback if tkextrafont is not available

from hardware import *
from jep106 import *
from memory import *

from about import *
import mem_helpers
from mem_helpers import *
from mlc_tool import MLCTool, MLCDialog

__author__ = 'remittor'

from version import appver
win_caption = f"pyhwinfo v{appver} - memory info"

class WinVar(tk.Variable):
    _default = ""   # Value holder for strings variables

    def __init__(self, value, name = None, root = None):
        master = root if root else None
        value = self.value_to_str(value)
        tk.Variable.__init__(self, master, value, name)
        if value is not None:
            self._default = str(value)
        self.label = None

    def value_to_str(self, value):
        if isinstance(value, float) and math.isnan(value):
            return ''
        if isinstance(value, float):
            return str(round(value, 2))
        return str(value)

    def set(self, value, style = None):
        if self.label:
            if style is None:
                self.label.configure(style='fixV.TLabel')
            else:
                self.label.configure(style=style)
        value = str(value)
        return self._tk.globalsetvar(self._name, value)

    def get(self):
        value = self._tk.globalgetvar(self._name)
        if isinstance(value, str):
            return value
        return str(value)
        
    @property
    def value(self): 
        return self.get()

    @value.setter 
    def value(self, val): 
        self.set(val)

def get_pretty_vendor_name(name_or_vid):
    if isinstance(name_or_vid, int):
        vid = name_or_vid
        if vid not in jep106:
            return f'0x{vid:04X}'
        name = jep106[vid]
    else:
        name = name_or_vid
    name = name + ' '
    name = name.replace(' Corporation ', ' ')
    name = name.replace(' Corp ', ' ')
    name = name.replace(' Corp. ', ' ')
    name = name.replace(' Co ', ' ')
    name = name.replace(' Incorporated ', ' ')
    name = name.replace(' Inc. ', ' ')
    name = name.replace(' Inc ', ' ')
    name = name.replace(' Ltd. ', ' ')
    name = name.replace(' Ltd ', ' ')
    name = name.replace(' Technologies ', ' Tech ')
    name = name.replace(' Technology ', ' Tech ')
    name = name.replace(' Limited ', ' ')
    name = name.replace(' Laboratories ', ' Lab ')
    name = name.replace('  ', ' ')
    return name.strip()

class WindowMemory():
    def __init__(self):
        global win_caption
        self.root = tk.Tk()
        load_extrafont(self.root)
        self.root.title(win_caption)
        self.root.resizable(False, False)
        self.init_screen()
        self.init_styles()
        self.vars = types.SimpleNamespace()
        self.test = False
        self.sdk_inited = False
        self.mem_info = None
        self.advanced_tooltip = AdvancedTooltip(self.root)
        self.m_inf = mem_helpers.m_inf
        self.mlc_tool = MLCTool(self.root)
        self.mlc_dialog = None

    def init_screen(self):
        #ctypes.windll.user32.SetProcessDPIAware()
        pass
        
    def get_screen_size(self):   
        user32 = ctypes.windll.user32
        width  = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        return width, height
        
    def init_styles(self):
        try:
            self.root.load_font("styles/IntelOneMono-Medium.ttf")
        except:
            pass  # Continue if font loading fails
        screen_size = self.get_screen_size()
        print(f'{screen_size=}')
        scr_h = screen_size[1]
        if scr_h <= 900:
            fs8 = 5
            fs9 = 6
            fs10 = 7
        elif scr_h <= 1000:
            fs8 = 6
            fs9 = 7
            fs10 = 8
        elif scr_h <= 1100:
            fs8 = 7
            fs9 = 8
            fs10 = 9
        else:
            fs8 = 8
            fs9 = 9
            fs10 = 10
        
        self.fs8 = fs8
        self.fs9 = fs9
        self.fs10 = fs10
            
        style = ttk.Style()
        style.configure('Title.TLabel', font=('Segoe UI', fs10))
        style.configure("TRadiobutton", font=('Segoe UI', fs9))
        style.configure("TCombobox", font=('Segoe UI', fs9))
        style.configure('Section.TLabelframe.Label', font=('Segoe UI', fs9))
        style.configure('Value.TLabel', font=('Consolas', fs10))
        style.configure('val.TLabel', font=('Consolas', fs10), padding=1, background="white", foreground="black", relief="groove", borderwidth=2)
        style.configure('Small.TLabel', font=('Consolas', fs8))

        xfont = ('Intel One Mono Medium', fs10)
        ufont = ('Segoe UI', fs10)

        style.configure('fixT.TLabel',         font=xfont, padding=0)
        style.configure('fixV.TLabel',         font=xfont, padding=0, background="white",   foreground="black", relief="groove", borderwidth=2)
        style.configure('fixV2.TLabel',        font=ufont, padding=0, background="white",   foreground="black", relief="groove", borderwidth=2)
        style.configure('fixA.TLabel',         font=xfont)

        # Light green for JEDEC compliant
        style.configure('fixV_valid.TLabel',   font=xfont, padding=0, background="#90EE90", foreground="black", relief="groove", borderwidth=2)
        # Bright green for optimal DDR5 values
        style.configure('fixV_optim.TLabel',   font=xfont, padding=0, background="#00FF7F", foreground="black", relief="groove", borderwidth=2)
        # Light yellow for tight timing
        style.configure('fixV_tight.TLabel',   font=xfont, padding=0, background="#FFFF99", foreground="black", relief="groove", borderwidth=2)
        # Light red for violations
        style.configure('fixV_violat.TLabel',  font=xfont, padding=0, background="#FFB6C1", foreground="black", relief="groove", borderwidth=2)

    def create_window(self):
        self.create_menu()
        vv = self.vars
        mem = None
        if self.mem_info:
            mem = self.mem_info['memory']

        self.cpu_id = None
        if 'cpu' in self.mem_info and self.mem_info['cpu']:
            self.cpu_id = (self.mem_info['cpu']['family'] << 8) | self.mem_info['cpu']['model_id']

        self.dimm_count = 4

        # Main container
        main_frame = ttk.Frame(self.root, padding=(10, 3))
        main_frame.pack(fill=tk.BOTH, expand=True)

        cpu_frame = ttk.Frame(main_frame)
        cpu_frame.pack(fill=tk.X, pady=1)
        ttk.Label(cpu_frame, text="CPU:", style='Title.TLabel').pack(side=tk.LEFT, padx = 5, pady = 1)
        vv.cpu_name = WinVar('?????????')
        cpu_label = ttk.Label(cpu_frame, textvariable=vv.cpu_name, style='Title.TLabel')
        cpu_label.pack(side=tk.LEFT, padx = 5, pady = 1)
        
        # Add advanced info button with info icon
        info_btn = tk.Button(cpu_frame, text="ℹ", font=("Segoe UI", self.fs10, "bold"), 
                            bg="#4CAF50", fg="white", width=3, height=1,
                            command=self.advanced_tooltip.show_advanced_info,
                            relief=tk.RAISED, borderwidth=2, cursor="hand2")
        info_btn.pack(side=tk.RIGHT, padx=3, pady=0)

        cap_btn = tk.Button(cpu_frame, text="📷", font=("Segoe UI", self.fs10, "bold"), 
                            bg="#4CAF50", fg="white", width=3, height=1,
                            command=self.take_screenshot,
                            relief=tk.RAISED, borderwidth=2, cursor="hand2")
        cap_btn.pack(side=tk.RIGHT, padx=3, pady=0)
        
        # Add tooltip for the info button
        ToolTip(info_btn, "Click for comprehensive DDR5 optimization guide, JEDEC validation info,\narchitectural insights, and advanced timing explanations not available\nin regular tooltips. Includes overclocking guidelines, platform-specific\noptimizations, and detailed technical references.")
        
        mboard_frame = ttk.Frame(main_frame)
        mboard_frame.pack(fill=tk.X, pady=1)
        ttk.Label(mboard_frame, text="Motherboard:", style='Title.TLabel').pack(side=tk.LEFT, padx = 5, pady = 1)
        vv.mb_name = WinVar('?????????')
        if False:
            mb = get_motherboard_info()
            vv.mb_name.value = mb['manufacturer'] + ' ' + mb['product']
        mb_label = ttk.Label(mboard_frame, textvariable=vv.mb_name, style='Title.TLabel')
        mb_label.pack(side=tk.LEFT, padx = 5, pady = 1)
        
        dimm_frame = ttk.LabelFrame(main_frame, text="DIMM", style='Section.TLabelframe')
        dimm_frame.pack(fill=tk.X, pady=3)
        
        dimm_frame2 = ttk.Frame(dimm_frame)
        dimm_frame2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        vv.dimm_radio = tk.StringVar()
        vv.dram_model_list = [ ]
        vv.die_vendor_list = [ ]
        
        def create_dimm(dnum, size, model, mc, ch, die, w = 0, anchor = 'center'):
            nonlocal vv, dimm_frame2
            slot = 'Slot ' + str(dnum)
            size = f'{size} GB' if size else ''
            model_t = 'Model' if size else ''
            model = str(model) if size else ''
            mc_t = 'MC' if size else ''
            mc = str(mc) if size else ''
            ch_t = 'CH' if size else ''
            ch = str(ch) if size else ''
            die_t = 'DIE' if size else ''
            die = str(die) if size else ''
            vstyle = 'fixV.TLabel' if size else 'Title.TLabel'
            vstyle2 = 'fixV2.TLabel' if size else 'Title.TLabel'
            vstyle3 = 'val.TLabel' if size else 'Title.TLabel'
            frame = ttk.Frame(dimm_frame2)
            frame.pack(fill=tk.X, pady=1)
            font = ('Segoe UI', self.fs9)
            radio_btn = tk.Radiobutton(frame, text=slot, font=font, variable=vv.dimm_radio, value=str(dnum), command=self.on_radio_select)
            radio_btn.pack(side=tk.LEFT)
            if not size:
                radio_btn.config(state = tk.DISABLED)
            dram_var = WinVar(model)
            vv.dram_model_list.append( dram_var )
            die_var = WinVar(die)
            vv.die_vendor_list.append( die_var )
            ttk.Label(frame, text=size, style=vstyle, width=6, anchor=anchor).pack(side=tk.LEFT)
            ttk.Label(frame, text=model_t, style='Title.TLabel', width=6, anchor='e').pack(side=tk.LEFT)
            ttk.Label(frame, textvariable=dram_var, style=vstyle2, width=38, anchor='center').pack(side=tk.LEFT)
            ttk.Label(frame, text=mc_t, style='Title.TLabel', width=3, anchor='e').pack(side=tk.LEFT)
            ttk.Label(frame, text=mc, style=vstyle, width=2, anchor=anchor).pack(side=tk.LEFT)
            ttk.Label(frame, text=ch_t, style='Title.TLabel', width=3, anchor='e').pack(side=tk.LEFT)
            ttk.Label(frame, text=ch, style=vstyle, width=2, anchor=anchor).pack(side=tk.LEFT)
            ttk.Label(frame, text=die_t, style='Title.TLabel', width=3, anchor='e').pack(side=tk.LEFT)
            ttk.Label(frame, textvariable=die_var, style=vstyle2, width=15, anchor='center').pack(side=tk.LEFT)
            
        self.page_dict = { }
        self.page_list = [ ]
        self.dimm_map = { }
        dnum = 0
        for mc in mem['mc']:
            mc_num = mc['controller']
            self.page_dict[mc_num] = { }
            chlst = [ mc['channels'][0], mc['channels'][1] ]
            for pnum in range(0, 2):
                size = 0
                ch_num_list = [ ]
                ch_tag_list = [ ]
                for cnum, ch in enumerate(chlst):
                    ch_num = ch['__channel']
                    if not mc_num in self.page_dict or not ch_num in self.page_dict[mc_num]:
                        if mc_num not in self.page_dict:
                            self.page_dict[mc_num] = { }
                        page = { 'mc': mc_num, 'ch': ch_num, 'frame': None }
                        self.page_dict[mc_num][ch_num] = page
                        self.page_list.append(page)
                    if pnum == 0:
                        tag = 'L' if ch['DIMM_L_MAP'] == 0 else 'S'
                    else:
                        tag = 'S' if ch['DIMM_L_MAP'] == 0 else 'L'
                    sz = ch[f'Dimm_{tag}_Size']
                    if sz > 0:
                        ch_num_list.append(ch_num)
                        ch_tag_list.append(tag)
                        size += sz
                size = size // 2
                self.dimm_map[dnum] = { 'mc': mc_num, 'ch': ch_num_list, 'CH': '?', 'tag': ch_tag_list, 'size': size }
                dnum += 1
        
        self.current_slot = None
        for dnum in range(0, self.dimm_count):
            if dnum not in self.dimm_map:
                break
            mc_num = self.dimm_map[dnum]['mc']
            mc = mem['mc'][mc_num]
            ch_num_list = self.dimm_map[dnum]['ch']
            ch_tag_list = self.dimm_map[dnum]['tag']
            ch_name = ''
            size = self.dimm_map[dnum]['size']
            model = '????????'
            die_name = '???????'
            if size and (len(ch_tag_list) == 1 or (len(ch_tag_list) == 2 and ch_tag_list[0] == ch_tag_list[1] )):
                ch_name = 'A' if ch_tag_list[0] == 'L' else 'B'
            if size and self.current_slot is None:
                self.current_slot = dnum
                self.current_mc = mc_num
                self.current_ch = ch_num_list[0]
            create_dimm(dnum, size, model, mc_num, ch_name, die_name)

        if self.current_slot is not None:
            vv.dimm_radio.set(str(self.current_slot))
        
        dram_ext_frame = ttk.Frame(main_frame)
        dram_ext_frame.pack(fill=tk.X, pady=1)

        vv.SPD_name = WinVar('???????')
        ttk.Label(dram_ext_frame, text='SPD', style='Title.TLabel', width=4, anchor='e').pack(side=tk.LEFT)
        ttk.Label(dram_ext_frame, textvariable=vv.SPD_name, style='fixV2.TLabel', width=36, anchor='center').pack(side=tk.LEFT)

        ttk.Label(dram_ext_frame, text=' ', style='Title.TLabel', width=2, anchor='e').pack(side=tk.LEFT, fill=tk.X, expand = True)
        
        vv.PMIC_name = WinVar('???????')
        ttk.Label(dram_ext_frame, text='PMIC', style='Title.TLabel', width=5, anchor='e').pack(side=tk.LEFT)
        ttk.Label(dram_ext_frame, textvariable=vv.PMIC_name, style='fixV2.TLabel', width=36, anchor='center').pack(side=tk.LEFT)
        
        freq_volt_frame = ttk.Frame(main_frame)
        freq_volt_frame.pack(fill=tk.X, pady=0)

        freq_chan_frame = ttk.Frame(freq_volt_frame)
        freq_chan_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=3)
        
        # Frequency information
        freq_frame = ttk.LabelFrame(freq_chan_frame, text="Frequency", style='Section.TLabelframe')
        freq_frame.pack(side=tk.TOP, fill=tk.Y, expand=False, padx=5, pady=0)

        def create_freq_col(vlist: list, w, anchor = 'center'):
            nonlocal freq_frame
            col = ttk.Frame(freq_frame)
            col.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=1)
            for value in vlist:
                vstyle = 'fixT.TLabel'
                if isinstance(value, str):
                    vstyle = 'fixT.TLabel'
                    ttk.Label(col, text=value, style=vstyle, width=w, anchor=anchor).pack(fill=tk.X, pady=1)
                else:    
                    vstyle = 'fixV.TLabel'
                    ttk.Label(col, textvariable=value, style=vstyle, width=w, anchor=anchor).pack(fill=tk.X, pady=1)
            
        vv.BCLK_M = WinVar('???')
        vv.MCLK_RATIO = WinVar('??')
        vv.MCLK_FREQ  = WinVar('???')
        vv.BCLK_U = WinVar('???')
        vv.UCLK_RATIO = WinVar('???')
        vv.UCLK_FREQ  = WinVar('???')
        
        create_freq_col([ "", "MCLK", "UCLK" ], w = 5)
        create_freq_col([ "Rate", vv.MCLK_RATIO, vv.UCLK_RATIO ], w = 6)
        create_freq_col([ "", "x", "x" ], w = 1)
        create_freq_col([ "BCLK", vv.BCLK_M, vv.BCLK_U ], w = 8)
        create_freq_col([ "", "=", "=" ], w = 1)
        create_freq_col([ "Frequency", vv.MCLK_FREQ, vv.UCLK_FREQ ], w = 10)
        create_freq_col([ "", "MHz", "MHz" ], w = 4, anchor = tk.W)

        # Channel info
        channel_frame = ttk.Frame(freq_chan_frame)
        channel_frame.pack(side=tk.BOTTOM, fill=tk.X, expand=False, pady=(3,0))
        
        vv.chan_count = WinVar('?')
        ttk.Label(channel_frame, text="Channels", width=10, anchor='e').pack(side=tk.LEFT)
        ttk.Label(channel_frame, textvariable=vv.chan_count, width=2, style='val.TLabel', anchor='center').pack(side=tk.LEFT, padx=1)
        
        vv.gear_mode = WinVar('?')
        ttk.Label(channel_frame, text="Gear Mode", width=11, anchor='e').pack(side=tk.LEFT)
        ttk.Label(channel_frame, textvariable=vv.gear_mode, width=2, style='val.TLabel', anchor='center').pack(side=tk.LEFT, padx=1)

        vv.mem_freq = WinVar('????')
        ttk.Label(channel_frame, text="Speed", width=7, anchor='e').pack(side=tk.LEFT)
        ttk.Label(channel_frame, textvariable=vv.mem_freq, width=6, style='fixV.TLabel', anchor='center').pack(side=tk.LEFT, padx=1)
        ttk.Label(channel_frame, text="MT/s", width=5, anchor='w').pack(side=tk.LEFT)
        
        # Sensors info
        sens_frame = ttk.LabelFrame(freq_volt_frame, text="DIMM Sensors", style='Section.TLabelframe')
        sens_frame.pack(fill=tk.BOTH, expand=True, pady=0)
        
        def create_sens_val(sframe, name, value, vt, w = 6):
            nonlocal vv
            var = WinVar(value)
            setattr(vv, 'sens_' + name.replace('.', '_'), var)
            frame = ttk.Frame(sframe)
            frame.pack(fill=tk.X, pady=1)
            ttk.Label(frame, text=name, width=w, style='fixT.TLabel', anchor=tk.W).pack(side=tk.LEFT)
            ttk.Label(frame, textvariable=var, width=7, style='fixV.TLabel', anchor='center').pack(side=tk.LEFT)
            if vt:
                ttk.Label(frame, text=vt, width=2, style='Title.TLabel', anchor='w').pack(side=tk.LEFT)
            
        sensA = ttk.Frame(sens_frame)
        sensA.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)
        create_sens_val(sensA, 'VDD',  '?????', 'V')
        create_sens_val(sensA, 'VDDQ', '?????', 'V')
        create_sens_val(sensA, 'VPP',  '?????', 'V')
        create_sens_val(sensA, 'VIN',  '?????', 'V')

        sensB = ttk.Frame(sens_frame)
        sensB.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)
        create_sens_val(sensB, 'Temp', '?????', '°C')
        create_sens_val(sensB, '1.8V', '?????', 'V')
        create_sens_val(sensB, '1.0V', '?????', 'V')

        # Mem Cotroller Settings
        ctrl_frame = ttk.LabelFrame(main_frame, text="Common Settings", style='Section.TLabelframe')
        ctrl_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def create_col_ctrl(elems, wn = 8, wv = 4):
            nonlocal vv, ctrl_frame
            col = ttk.Frame(ctrl_frame)
            col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            for name, value in elems:
                vt = None
                if value.startswith('@'):
                    vt = value[1:]
                    value = '??'
                if name == '':
                    var = value
                else:
                    var = WinVar(value)
                    var_name = name
                    if name == 'VDDQ_TX' and vt == 'A':
                        var_name += '_ICCMAX'
                    setattr(vv, var_name, var)
                frame = ttk.Frame(col)
                frame.pack(fill=tk.X, pady=1)
                ttk.Label(frame, text=name, style='fixT.TLabel', width=wn, anchor=tk.W).pack(side=tk.LEFT)
                label_widget = ttk.Label(frame, textvariable=var, style='fixV.TLabel', width=wv, anchor='center')
                label_widget.pack(side=tk.LEFT)
                var.label = label_widget
                if vt:
                    ttk.Label(frame, text=vt, width=len(vt)+1, style='Title.TLabel', anchor='w').pack(side=tk.LEFT)

        elems = [
            ( "DDR_OVERCLOCK", '??' ),
            ( "TIMING_RUNTIME_OC", '??' ),
            ( "POWER_LIMIT", '??' ),     # On / Off
        ]
        create_col_ctrl(elems, wn = 17)
        elems = [
            ( "BCLK_OC", '??' ),
            ( "OC_ENABLED", '??' ),
        ]
        create_col_ctrl(elems, wn = 10)
        elems = [
            ( "AC_LL", '' ),
            ( "DC_LL", '' ),
            ( "IccMax", '@A' ),
        ]
        create_col_ctrl(elems, wn = 6, wv = 6)
        elems = [
            ( "SA_VID", '@V' ),
            ( "VDDQ_TX", '@V' ),
        ]
        create_col_ctrl(elems, wn = 7, wv = 7)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill = 'both', expand = True, padx = 1, pady = 1)

        self.vars.page = { }
        for mc_num, chan in self.page_dict.items():
            self.vars.page[mc_num] = { }
            for ch_num, page in self.page_dict[mc_num].items():
                self.vars.page[mc_num][ch_num] = types.SimpleNamespace()
                self.create_notebook_page(mc_num, ch_num)

    def create_notebook_page(self, mc_num, ch_num):    
        vv = self.vars.page[mc_num][ch_num]
        page = self.page_dict[mc_num][ch_num]
        page_frame = ttk.Frame(self.notebook)
        self.notebook.add(page_frame, text = f"  MC {mc_num} : CH {ch_num}  ")
        page['frame'] = page_frame
        timings_frame = page_frame

        mem = self.mem_info['memory'] if self.mem_info else None

        def draw_timing_label_and_value(base_frame, name, var, wn, wv):
            nonlocal vv
            frame = ttk.Frame(base_frame)
            frame.pack(fill=tk.X, pady=1)
            ttk.Label(frame, text=name, style='fixT.TLabel', width=wn, anchor=tk.W).pack(side=tk.LEFT)
            label_widget = ttk.Label(frame, textvariable=var, style='fixV.TLabel', width=wv, anchor='center')
            label_widget.pack(side=tk.LEFT)
            # Store reference to label widget for style changes
            var.label = label_widget
            # Add tooltip if formula exists
            if name in self.m_inf.timing_formulas:
                tooltip_text = self.m_inf.timing_formulas[name]
                # Add JEDEC validation info to tooltip during update
                ToolTip(label_widget, tooltip_text)
        
        base_timings_frame = ttk.Frame(timings_frame)
        base_timings_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady = 2)

        def create_col_timings(tlist, wn = 8, wv = 5, frame = None):
            nonlocal vv, base_timings_frame
            if not frame:
                frame = base_timings_frame
            col = ttk.Frame(frame)
            col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)
            for item in tlist:
                value = ''
                if isinstance(item, str):
                    name = item
                else:
                    name, value = item
                NAME = name
                if '=' in name:
                    NAME, name = name.split('=')
                var = WinVar(value)
                setattr(vv, name, var)
                _wn = wn
                _wv = wv
                if name == 'tREFI':
                    _wn = 6
                    _wv = 7
                if name == 'RTL':
                    _wn = 3
                    _wv = 12
                draw_timing_label_and_value(col, NAME, var, _wn, _wv)

        col_timings = [
            ( "---",    "" ),
            ( "tCL",    '??' ),
            ( "tRCD",   '??' ),
            ( "tRCDW",  ''   ),
            ( "tRP",    '??' ),
            ( "tRAS",   '??' ),
            ( "tRC",    '??' ),
        ]
        create_col_timings(col_timings, wn = 7)
        
        col_timings = [
            ( "tCR",    '??' ),
            ( "tCWL",   '??' ),
            ( "tRFC",   '??' ),
            ( "tRFC2",  ''   ),
            ( "tRFCpb", '??' ),
            ( "tXSR",   '??' ),
            ( "tREFI",  '??' ),
        ]
        create_col_timings(col_timings)
        
        col_timings = [
            ( "tFAW",    '??' ),
            ( "tRRD_L",  '??' ),
            ( "tRRD_S",  '??' ),
            ( "tRDPRE",  '??' ),
            ( "tRDPDEN", '??' ),
            ( "tRTP",    '??' ),
            ( "tREFIx9", '??' ),
        ]
        create_col_timings(col_timings)
        
        col_timings = [
            ( "tWR",     '??' ),
            ( "tWTR_L",  '??' ),
            ( "tWTR_S",  '??' ),
            ( "tWRPRE",  '??' ),
            ( "tWRPDEN", '??' ),
            ( "tWTP",    ''   ),
            ( "tREFSBRD", '??' ),
        ]
        create_col_timings(col_timings)

        col_timings = [
            ( "tCKE",    '??' ),
            ( "tCPDED",  '??' ),
            ( "tXP",     '??' ),
            ( "tXPDLL",  '??' ),
            ( "tPRPDEN", '??' ),
            ( "tXSDLL",   ''   ),
            ( "RTL",     '??/??/??/??' ),
        ]
        create_col_timings(col_timings, wv = 6)
        
        adv_frame = ttk.Frame(timings_frame)
        adv_frame.pack(fill=tk.BOTH, expand=True, pady=7, padx=3)

        def create_adv_timings(tlist, caption, wn = 9, wv = 5):
            nonlocal vv, adv_frame
            col = ttk.LabelFrame(adv_frame, text=caption, style='Section.TLabelframe')
            col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)
            for name, value in tlist:
                if name == '' or not name.startswith('t'):
                    var = str(value)
                else:
                    var = WinVar(value)
                    setattr(vv, name, var)
                _wn = wn
                _wv = wv
                draw_timing_label_and_value(col, name, var, _wn, _wv)

        adv_timings = [
            ( "tRDRD_sg", '??' ),
            ( "tRDWR_sg", '??' ),
            ( "tWRRD_sg", '??' ),
            ( "tWRWR_sg", '??' ),
        ]
        create_adv_timings(adv_timings, "Same Bank Group")
        adv_timings = [
            ( "tRDRD_dg", '??' ),
            ( "tRDWR_dg", '??' ),
            ( "tWRRD_dg", '??' ),
            ( "tWRWR_dg", '??' ),
        ]
        create_adv_timings(adv_timings, "Different Bank Group")
        adv_timings = [
            ( "tRDRD_dr", '??' ),
            ( "tRDWR_dr", '??' ),
            ( "tWRRD_dr", '??' ),
            ( "tWRWR_dr", '??' ),
        ]
        create_adv_timings(adv_timings, "Same DIMM")
        adv_timings = [
            ( "tRDRD_dd", '??' ),
            ( "tRDWR_dd", '??' ),
            ( "tWRRD_dd", '??' ),
            ( "tWRWR_dd", '??' ),
        ]
        create_adv_timings(adv_timings, "Different DIMM")

        ext_timings_frame = ttk.Frame(timings_frame)
        ext_timings_frame.pack(fill=tk.BOTH, expand=True, padx=5)

        col_timings = [ "DEC_tCWL", "ADD_tCWL", "tPPD", ]
        create_col_timings(col_timings, wn = 8, frame = ext_timings_frame)

        col_timings = [ "tCSL", "tCSH", "tRFM", ]
        create_col_timings(col_timings, wn = 5, frame = ext_timings_frame)

        col_timings = [ "oref_ri", "tZQOPER", "tMOD", ]
        create_col_timings(col_timings, wn = 7, frame = ext_timings_frame)

        col_timings = [ "X8_DEVICE" , "PullUpDrv", "PullDownDrv", ]
        create_col_timings(col_timings, wn = 11, frame = ext_timings_frame)

        col_timings = [ "tWR=tWR_a", "tWTR_L=tWTR_L_alt", "tWTR_S=tWTR_S_alt" ]
        create_col_timings(col_timings, wn = 6, frame = ext_timings_frame)

        # ODT section
        odt_frame = ttk.Frame(timings_frame)
        odt_frame.pack(fill=tk.BOTH, expand=True, pady=2)

        odt_rtt_frame = ttk.LabelFrame(odt_frame, text="ODT Rtt", style='Section.TLabelframe')
        odt_rtt_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=2, padx=3)

        odt_cxA_frame = ttk.LabelFrame(odt_frame, text="ODT Cfg Group A", style='Section.TLabelframe')
        odt_cxA_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=2, padx=3)

        odt_cxB_frame = ttk.LabelFrame(odt_frame, text="ODT Cfg Group B", style='Section.TLabelframe')
        odt_cxB_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=2, padx=3)

        odt_vref_frame = ttk.LabelFrame(odt_frame, text="Vref", style='Section.TLabelframe')
        odt_vref_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=2, padx=3)

        def create_odt_val(frame, group, tlist, wn = 8, wv = 4):
            nonlocal vv
            col = ttk.Frame(frame)
            col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)
            for name in tlist:
                vvname = 'ODT_' + name
                if group:
                    vvname += f'_{group}'
                var0 = WinVar('')
                setattr(vv, vvname + '__0', var0)
                var1 = WinVar('')
                setattr(vv, vvname + '__1', var1)
                _wn = wn
                _wv = wv
                frame = ttk.Frame(col)
                frame.pack(fill=tk.X, pady=1)
                ttk.Label(frame, text=name, style='fixT.TLabel', width=_wn, anchor=tk.W).pack(side=tk.LEFT)
                ttk.Label(frame, textvariable=var0,  style='fixV.TLabel', width=_wv, anchor='center').pack(side=tk.LEFT)
                if name != 'Loopback':
                    ttk.Label(frame, textvariable=var1,  style='fixV.TLabel', width=_wv, anchor='center').pack(side=tk.LEFT)

        create_odt_val(odt_rtt_frame, None, [ "Wr", "Park", "ParkDqs" ], wn = 7 )
        create_odt_val(odt_rtt_frame, None, [ "NomRd", "NomWr", "Loopback" ], wn = 8 )
        create_odt_val(odt_cxA_frame, 'A', [ "CA", "CS", "CK" ], wn = 3 )
        create_odt_val(odt_cxB_frame, 'B', [ "CA", "CS", "CK" ], wn = 3 )
        create_odt_val(odt_vref_frame, 'V', [ "CA", "CS", "DQ" ], wn = 3 )

    def update(self, slot_id = None):
        vv = self.vars
        if slot_id is None:
            slot_id = self.current_slot
        cap = self.mem_info['CAP']
        msr = self.mem_info['MSR'] if 'MSR' in self.mem_info else { }
        mem = self.mem_info['memory']
        dimm = None
        for elem in self.mem_info['memory']['DIMM']:
            if elem['slot'] == slot_id:
                dimm = elem
                break
        
        if not dimm:
            raise RuntimeError(f'slot = {slot_id}')
        
        pmic = dimm['PMIC'] if dimm and 'PMIC' in dimm else None
        
        vv.cpu_name.value = self.mem_info['cpu']['name']
        if 'stepping' in self.mem_info['cpu']:
            fam = self.mem_info['cpu']['family']
            model = self.mem_info['cpu']['model_id']
            step = self.mem_info['cpu']['stepping']
            vv.cpu_name.value += f'  [{fam:02X}:{model:02X}:{step:02X}]'

        board = self.mem_info['board']
        vv.mb_name.value = board['manufacturer'] + ' ' + board['product']
        if 'BIOS' in self.mem_info and 'MICROCODE_VER' in self.mem_info['BIOS']:
            ver = self.mem_info['BIOS']['MICROCODE_VER']
            vv.mb_name.value += f'  [BIOS: 0x{ver:X}]'

        for elem in vv.dram_model_list:
            elem.set('')
        
        for elem in vv.die_vendor_list:
            elem.set('')
        
        cur_dimm = None
        slot_count = 0
        for elem in self.mem_info['memory']['DIMM']:
            slot = elem['slot']
            if slot == slot_id:
                cur_dimm = elem
            slot_count += 1
            spd = elem['SPD'] if 'SPD' in elem else None
            if spd:
                vendor = get_pretty_vendor_name(spd['vendorid'])
                ranks = '  (' + str(spd['ranks']) + 'R)'
                vv.dram_model_list[slot].value = vendor + '  ' + spd['part_number'] + ranks
            if spd and 'die_vendorid' in spd and spd['die_vendorid']:
                vendor = get_pretty_vendor_name(spd['die_vendorid'])
                if 'die_stepping' in spd:
                    vendor += f' [0x{spd["die_stepping"]:02X}]'
                vv.die_vendor_list[slot].value = vendor

        vv.SPD_name.value = ''
        if cur_dimm and 'spd_vid' in cur_dimm and cur_dimm['spd_vid']:
            name = get_pretty_vendor_name(cur_dimm['spd_vid'])
            if 'SPD' in cur_dimm and 'revision' in cur_dimm['SPD'] and cur_dimm['SPD']['revision']:
                name += ' [' + cur_dimm['SPD']['revision'] + ']'
            vv.SPD_name.value = name
        
        vv.PMIC_name.value = ''
        if cur_dimm and 'PMIC' in cur_dimm and cur_dimm['PMIC']:
            name = get_pretty_vendor_name(cur_dimm['PMIC']['vid'])
            if 'revision' in cur_dimm['PMIC'] and cur_dimm['PMIC']['revision']:
                name += ' [' + cur_dimm['PMIC']['revision'] + ']'
            vv.PMIC_name.value = name
        
        MCLK_FREQ = ''
        QCLK_RATIO = 0
        vv.MCLK_RATIO.value = ''
        vv.BCLK_M.value = mem['BCLK_FREQ']
        vv.MCLK_FREQ.value = ''

        if self.cpu_id in i12_FAM and mem['SA']['QCLK_RATIO']:
            QCLK_RATIO = mem['SA']['QCLK_RATIO']
            vv.MCLK_RATIO.value = QCLK_RATIO
            MCLK_FREQ = mem['SA']['QCLK_FREQ']
            base_freq = 133.34 if mem['SA']['QCLK_REFERENCE'] == 0 else mem['SA']['QCLK_FREQ'] / QCLK_RATIO
            vv.BCLK_M.value = round(base_freq, 2)

        if self.cpu_id in i15_FAM and 'QCLK_RATIO' in mem and mem['QCLK_RATIO']:
            # ref: https://skatterbencher.com/2024/10/24/arrow-lake-memss-overclocking/
            QCLK_FREQ = mem['QCLK_FREQ']
            CMI_RATIO = mem['QCLK_RATIO']
            vv.MCLK_RATIO.value = CMI_RATIO
            MCLK_FREQ = QCLK_FREQ
            vv.BCLK_M.value = round(QCLK_FREQ / CMI_RATIO, 2)

        if MCLK_FREQ:
            vv.MCLK_FREQ.value = round(MCLK_FREQ, 2)
        
        vv.BCLK_U.value = mem['BCLK_FREQ']
        UCLK_RATIO = None
        if msr and 'VF' in msr:
            UCLK_RATIO = msr.get('VF', {}).get('RING', {}).get('MaxOcRatio', None)
        if not UCLK_RATIO:
            UCLK_RATIO = mem['SA']['UCLK_RATIO']
        vv.UCLK_RATIO.value = UCLK_RATIO
        vv.UCLK_FREQ.value = round(mem['BCLK_FREQ'] * UCLK_RATIO, 2)
        
        if mem['mc'][0]['DDR_ver'] == 5:
            max_chan_count = len(mem['mc']) * len(mem['mc'][0]['channels'])
            chan_count = 0
            for mc in mem['mc']:
                for ch in mc['channels']:
                    if ch['Dimm_L_Size'] > 0 or ch['Dimm_S_Size'] > 0:
                        chan_count += 1
            if chan_count > max_chan_count:
                chan_count = max_chan_count
            vv.chan_count.value = chan_count
        else:
            vv.chan_count.value = '?'
        
        gear = ''
        if 'GEAR' in mem:
            gear = mem['GEAR']
        elif 'GEAR' in mem['mc'][0]['channels'][0]['info']:
            gear = mem['mc'][0]['channels'][0]['info']['GEAR']
        vv.gear_mode.value = gear
       
        vv.mem_freq.value = ''
        if MCLK_FREQ:
            speed = int(MCLK_FREQ * 2)
            if speed >= 990:
                if str(int(speed / 10)).endswith('9'):
                    speed += 10
                if str(int(speed / 10)).endswith('0'):
                    speed = int(speed / 10) * 10
            vv.mem_freq.value = speed

        vv.sens_Temp.value = ''
        vv.sens_VDD.value = ''
        vv.sens_VDDQ.value = ''
        vv.sens_VPP.value = ''
        vv.sens_VIN.value = ''
        vv.sens_1_8V.value = ''
        vv.sens_1_0V.value = ''
        if pmic and 'SWA' in pmic:
            vv.sens_VDD.value = pmic['SWA']
            vv.sens_VDDQ.value = pmic['SWC']
            vv.sens_VPP.value = pmic['SWD']
        if pmic and 'VIN' in pmic:
            vv.sens_VIN.value = pmic['VIN']
        if pmic and '1.8V' in pmic:
            vv.sens_1_8V.value = pmic['1.8V']
        if pmic and '1.0V' in pmic:
            vv.sens_1_0V.value = pmic['1.0V']
        if dimm and 'temp' in dimm:
            vv.sens_Temp.value = dimm['temp']
        
        vv.DDR_OVERCLOCK.value = 'ON' if cap['DDR_OVERCLOCK'] else 'off'
        vv.TIMING_RUNTIME_OC.value = 'ON' if mem['MC_TIMING_RUNTIME_OC_ENABLED'] else 'off'
        vv.BCLK_OC.value = 'ON' if cap['BCLKOCRANGE'] == 3 else 'off'
        vv.OC_ENABLED.value = 'ON' if cap['OC_ENABLED'] else 'off'
        msrSA = msr.get('VF', {}).get('SYSTEM_AGENT', None) if msr else None
        vv.SA_VID.value = ''
        if mem['SA']['SA_VOLTAGE']:
            vv.SA_VID.value = mem['SA']['SA_VOLTAGE']
        elif msrSA:
            VoltageTargetMode = msrSA['VoltageTargetMode']
            VoltageTarget = msrSA['VoltageTarget']
            VoltageOffset = msrSA['VoltageOffset']
            if VoltageTargetMode == 'OVERRIDE':
                vv.SA_VID.value = round(VoltageTarget, 3)
            elif VoltageOffset < 0.0:
                vv.SA_VID.value = str(round(VoltageOffset, 3))
            elif VoltageOffset >= 0.0:
                vv.SA_VID.value = '+' + str(round(VoltageOffset, 3))
        vv.POWER_LIMIT.value = ''
        if 'LIMIT2_ENABLE' in mem['POWER']:
            if mem['POWER']['LIMIT2_ENABLE'] == 0 and mem['POWER']['LIMIT1_ENABLE'] == 0:
                vv.POWER_LIMIT.value = 'off'
            else:
                vv.POWER_LIMIT.value = 'ON'
        elif msr and 'DDR_RAPL' in msr:
            if msr['DDR_RAPL']['Limit2Enable'] == 0 and msr['DDR_RAPL']['Limit1Enable'] == 0:
                vv.POWER_LIMIT.value = 'off'
            else:
                vv.POWER_LIMIT.value = 'ON'
        
        if 'REQ_VDDQ_TX_VOLTAGE' in mem and mem['REQ_VDDQ_TX_VOLTAGE']:
            vv.VDDQ_TX.value = mem['REQ_VDDQ_TX_VOLTAGE']
        elif 'VccDDQ' in mem and mem['VccDDQ']:
            vv.VDDQ_TX.value = mem['VccDDQ']

        if msr and 'VR' in msr and 'AC_loadline' in msr['VR']:
            vv.AC_LL.value = msr['VR']['AC_loadline']
            vv.DC_LL.value = msr['VR']['DC_loadline']

        if msr and 'IccMaxValue' in msr and msr['IccMaxValue']:
            vv.IccMax.value = round(msr['IccMaxValue'], 1)
        
        for page in self.page_list:
            mc = page['mc']
            ch = page['ch']
            self.update_page(slot_id, mc, ch)
            chan = mem['mc'][mc]['channels'][ch]
            validate_timings(self, chan['info'], MCLK_FREQ, vv, self.vars.page[mc][ch])

        validate_voltages(self, dimm, MCLK_FREQ, vv)
        
        self.current_slot = slot_id
        
    def update_page(self, slot_id, mc_id, ch_id):
        mem = self.mem_info['memory']
        info = mem['mc'][mc_id]
        
        vv = self.vars.page[mc_id][ch_id]
        chan = mem['mc'][mc_id]['channels'][ch_id]
        ci = chan['info']
        mrs = ci['MRS'] if 'MRS' in ci else { }

        vv.tCL.value = ci['tCL']
        vv.tRCD.value = ci['tRCD']
        vv.tRCDW.value = ci['tRCDW'] if 'tRCDW' in ci else ''
        vv.tRP.value = ci['tRP']
        vv.tRAS.value = ci['tRAS']
        vv.tRC.value = ci['tRAS'] + ci['tRP']
        vv.tCR.value = ci['tCR']
        vv.tCWL.value = ci['tCWL']
        vv.tRFC.value = ci['tRFC'] if ci['tRFC'] else ''
        vv.tRFC2.value = ci['tRFC2'] if ci['tRFC2'] else ''
        vv.tRFCpb.value = ci['tRFCpb']
        vv.tXSR.value = ci['tXSR']
        vv.tREFI.value = ci['tREFI']
        vv.tFAW.value = ci['tFAW']
        vv.tRRD_L.value = ci['tRRD_L']
        vv.tRRD_S.value = ci['tRRD_S']
        vv.tRDPRE.value = ci['tRDPRE']
        vv.tRDPDEN.value = ci['tRDPDEN']
        if mrs and 'MR6' in mrs and mrs['MR6']['tRTP']:
            vv.tRTP.value = mrs['MR6']['tRTP']
        else:
            vv.tRTP.value = ci['tRTP'] if ci['tRTP'] else ''
        vv.tREFIx9.value = ci['tREFIx9']
        vv.tWR.value = ci['tWR']
        vv.tWTR_L.value = ci['tWTR_L']
        vv.tWTR_S.value = ci['tWTR_S']
        vv.tWRPRE.value = ci['tWRPRE']
        vv.tWRPDEN.value = ci['tWRPDEN']
        vv.tWTP.value = ''
        vv.tREFSBRD.value = ci['tREFSBRD']
        vv.tCKE.value = ci['tCKE']
        vv.tCPDED.value = ci['tCPDED']
        vv.tXP.value = ci['tXP']
        vv.tXPDLL.value = ci['tXPDLL'] if 'tXPDLL' in ci else ''
        vv.tXSDLL.value = ci['tXSDLL']
        vv.tPRPDEN.value = ci['tPRPDEN']
        rtl_list = [ '??', '??', '??', '??' ]
        for key, val in ci.items():
            if key.startswith('tRTL_'):
                num = int(key.split('_')[1])
                rtl_list[num] = str(val)
        vv.RTL.value = '/'.join(rtl_list)

        vv.tRDRD_sg.value = ci['tRDRD_sg']
        vv.tRDWR_sg.value = ci['tRDWR_sg']
        vv.tWRRD_sg.value = ci['tWRRD_sg']
        vv.tWRWR_sg.value = ci['tWRWR_sg']
        vv.tRDRD_dg.value = ci['tRDRD_dg']
        vv.tRDWR_dg.value = ci['tRDWR_dg']
        vv.tWRRD_dg.value = ci['tWRRD_dg']
        vv.tWRWR_dg.value = ci['tWRWR_dg']
        vv.tRDRD_dr.value = ci['tRDRD_dr']
        vv.tRDWR_dr.value = ci['tRDWR_dr']
        vv.tWRRD_dr.value = ci['tWRRD_dr']
        vv.tWRWR_dr.value = ci['tWRWR_dr']
        vv.tRDRD_dd.value = ci['tRDRD_dd']
        vv.tRDWR_dd.value = ci['tRDWR_dd']
        vv.tWRRD_dd.value = ci['tWRRD_dd']
        vv.tWRWR_dd.value = ci['tWRWR_dd']

        vv.DEC_tCWL.value = ci['DEC_tCWL'] if 'DEC_tCWL' in ci else ''
        vv.ADD_tCWL.value = ci['ADD_tCWL'] if 'ADD_tCWL' in ci else ''
        vv.tPPD.value = ci['tPPD']
        vv.tCSL.value = ci['tCSL']
        vv.tCSH.value = ci['tCSH']
        vv.tRFM.value = ci['tRFM']
        vv.oref_ri.value = ci['oref_ri']
        vv.tZQOPER.value = ci['tZQOPER'] if 'tZQOPER' in ci else ''
        vv.tMOD.value = ci['tMOD'] if 'tMOD' in ci else ''
        vv.X8_DEVICE.value = ci['X8_DEVICE'] if 'X8_DEVICE' in ci else ''
        vv.tWR_a.value = mrs['MR6']['WriteRecoveryTime'] if mrs and 'MR6' in mrs else ''
        vv.tWTR_L_alt.value = ci['tWTR_L_alt'] if 'tWTR_L_alt' in ci else ''
        vv.tWTR_S_alt.value = ci['tWTR_S_alt'] if 'tWTR_S_alt' in ci else ''
        
        def get_first_value(value, none_as = ''):
            if isinstance(value, list) and len(value) > 0:
                value = value[0] if len(value) > 0 else None
            if value is None and none_as is not None:
                return none_as
            return value

        def set_odt_val(mrs, mrs_name, name):
            nonlocal vv
            vvname0 = 'ODT_' + name + '__0'
            vvname1 = 'ODT_' + name + '__1'
            try:
                vv0 = getattr(vv, vvname0)
                vv1 = getattr(vv, vvname1)
            except AttributeError:
                return False
            if mrs_name not in mrs:
                vv0.value = ''
                vv1.value = ''
                return False
            if isinstance(mrs[mrs_name], list):
                vv0.value = mrs[mrs_name][0]
                vv1.value = mrs[mrs_name][1]
            else:
                vv0.value = mrs[mrs_name]
                vv1.value = ''
            return True
        
        if mrs:
            set_odt_val(mrs, 'RttWr', "Wr")
            set_odt_val(mrs, 'RttPark', "Park")
            set_odt_val(mrs, 'RttParkDqs', "ParkDqs")
            set_odt_val(mrs, 'RttLoopback', "Loopback")
            set_odt_val(mrs, 'RttNomWr', "NomWr")
            set_odt_val(mrs, 'RttNomRd', "NomRd")
            set_odt_val(mrs, 'RttCK_A', "CK_A")
            set_odt_val(mrs, 'RttCS_A', "CS_A")
            set_odt_val(mrs, 'RttCA_A', "CA_A")
            set_odt_val(mrs, 'RttCK_B', "CK_B")
            set_odt_val(mrs, 'RttCS_B', "CS_B")
            set_odt_val(mrs, 'RttCA_B', "CA_B")
            set_odt_val(mrs, 'VrefCA', "CA_V")
            set_odt_val(mrs, 'VrefCS', "CS_V")
            set_odt_val(mrs, 'VrefDQ', "DQ_V")
            vv.PullUpDrv.value   = mrs['MR5']['PullUpOutputDriverImpedance']   if 'MR5' in mrs else ''
            vv.PullDownDrv.value = mrs['MR5']['PullDownOutputDriverImpedance'] if 'MR5' in mrs else ''

        self.current_mc = mc_id
        self.current_ch = ch_id
    
    def refresh(self, update = True):
        if update:
            print('Refresh started...')
        self.update_hardware_info()
        if update:
            self.update()
            print('Main window refreshed!')

    def update_hardware_info(self):
        if self.test:
            with open('IMC.json', 'r', encoding='utf-8') as file:
                self.mem_info = json.load(file)
        else:
            from cpuidsdk64 import SdkInit
            from memspd import get_mem_spd_all
            if not self.sdk_inited:
                SdkInit(None, verbose = 0)
                self.sdk_inited = True
            self.mem_info = get_mem_spd_all(None, with_pmic = True, allinone = True)

    def on_radio_select(self):
        vv = self.vars
        slot = vv.dimm_radio.get()
        print(f"You selected DIMM: {slot}")
        self.current_slot = int(slot)
        self.update(slot_id = int(slot))
        
    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu = menubar)
        font = ('Segoe UI', 12)

        file_menu = tk.Menu(menubar, tearoff = 0, font = font)
        menubar.add_cascade(label = "  File  ", menu = file_menu)
        file_menu.add_command(label = "Save all data to JSON-file", font = font, command = self.wnd_menu_save_json)
        file_menu.add_separator()
        file_menu.add_command(label = "Exit", font = font, command = self.wnd_destroy)

        act_menu = tk.Menu(menubar, tearoff = 0, font = font)
        menubar.add_cascade(label = "  Actions  ", menu = act_menu)
        act_menu.add_command(label = "Refresh", font = font, command = self.wnd_menu_refresh)
        act_menu.add_command(label = "MLC tool", font = font, command = self.wnd_menu_mlc)

        info_menu = tk.Menu(menubar, tearoff = 0, font = font)
        menubar.add_cascade(label = "  Help  ", menu = info_menu)
        info_menu.add_command(label = "Optimization Guide", font = font, command = self.advanced_tooltip.show_advanced_info)
        info_menu.add_separator()
        info_menu.add_command(label = "About", font = font, command = self.wnd_menu_about)

    def wnd_destroy(self):
        self.root.destroy()
    
    def wnd_menu_refresh(self):
        self.refresh()
        
    def wnd_menu_about(self):
        AboutDialog(self.root, appver)

    def take_screenshot(self):
        import ctypes, mss, datetime
        hWnd = ctypes.windll.user32.GetForegroundWindow()
        if hWnd == 0:
            return
        rect = RECT()
        result = ctypes.windll.user32.GetWindowRect(hWnd, ctypes.byref(rect))
        if result != 0:
            dt = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
            fn = f'meminfo_{dt}.png'
            with mss.mss() as sct:
                monitor = { "left": rect.left, "top": rect.top, "width": rect.right - rect.left, "height": rect.bottom - rect.top }
                screenshot = sct.grab(monitor)
                mss.tools.to_png(screenshot.rgb, screenshot.size, output = fn)
                print(f'Screenshot saved to file "{fn}"')

    def wnd_menu_save_json(self):
        from datetime import datetime
        #print("Button Save clicked!")
        if 'time' in self.mem_info:
            dt = datetime.strptime(self.mem_info['time'], "%Y-%m-%d %H:%M:%S")
            dt = dt.strftime("%Y-%m-%d_%H%M")
        else:
            dt = datetime.now().strftime("%Y-%m-%d_%H%M")
        fn = f'IMC_{dt}.json'
        with open(fn, 'w') as file:
            json.dump(self.mem_info, file, indent = 4)
        print(f'File "{fn}" created')

    def wnd_menu_mlc(self):
        """Handle MLC button click - show MLC measurement dialog"""
        print("MLC Latency Test button clicked!")
        if not self.mlc_dialog:
            self.mlc_dialog = MLCDialog(self.root, self.mlc_tool)
        self.mlc_dialog.show_dialog()

if __name__ == "__main__":
    test = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            test = True

    win = WindowMemory()
    win.test = test
    win.update_hardware_info()
    win.create_window()
    win.update()

    win.root.mainloop()

