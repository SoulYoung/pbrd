"""Native Windows folder selection for the local editor (standard library only)."""
from pathlib import Path
import ctypes,os,threading
from ctypes import wintypes

_DIALOG_LOCK=threading.Lock()

class _Guid(ctypes.Structure):
    _fields_=[('a',ctypes.c_uint32),('b',ctypes.c_uint16),('c',ctypes.c_uint16),('d',ctypes.c_ubyte*8)]
    @classmethod
    def parse(cls,value):
        import uuid
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)

def _method(pointer,index,*arguments):
    table=ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,*arguments)(table[index])

def _check(result,operation):
    if result<0:raise ValueError(operation+'失败（0x%08X）'%(result&0xffffffff))

def _browse(initial):
    # Common Item Dialog in folder mode, rather than the legacy shell tree picker.
    # https://learn.microsoft.com/windows/win32/shell/common-file-dialog
    ole=ctypes.WinDLL('ole32');shell=ctypes.WinDLL('shell32')
    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD];ole.CoInitializeEx.restype=ctypes.c_long
    ole.CoCreateInstance.argtypes=[ctypes.POINTER(_Guid),ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(_Guid),ctypes.POINTER(ctypes.c_void_p)];ole.CoCreateInstance.restype=ctypes.c_long
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p];ole.CoTaskMemFree.restype=None
    shell.SHCreateItemFromParsingName.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,ctypes.POINTER(_Guid),ctypes.POINTER(ctypes.c_void_p)];shell.SHCreateItemFromParsingName.restype=ctypes.c_long
    _check(ole.CoInitializeEx(None,2),'初始化目录选择器')
    dialog=ctypes.c_void_p();folder=ctypes.c_void_p();item=ctypes.c_void_p();text=ctypes.c_void_p();selected=None
    try:
        clsid=_Guid.parse('DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7')
        iid=_Guid.parse('D57C7288-D4AD-4768-BE02-9D969532D960')
        shell_iid=_Guid.parse('43826D1E-E718-42EE-BC55-A1E261C37BFE')
        _check(ole.CoCreateInstance(ctypes.byref(clsid),None,1,ctypes.byref(iid),ctypes.byref(dialog)),'创建目录选择器')
        flags=wintypes.DWORD()
        _check(_method(dialog,10,ctypes.POINTER(wintypes.DWORD))(dialog,ctypes.byref(flags)),'读取窗口选项')
        _check(_method(dialog,9,wintypes.DWORD)(dialog,flags.value|0x20|0x40|0x800|0x8),'配置目录选择器')
        _check(_method(dialog,17,wintypes.LPCWSTR)(dialog,'选择 JSON 保存文件夹'),'设置窗口标题')
        _check(_method(dialog,18,wintypes.LPCWSTR)(dialog,'选择此文件夹'),'设置确认按钮')
        if initial:
            result=shell.SHCreateItemFromParsingName(initial,None,ctypes.byref(shell_iid),ctypes.byref(folder))
            if result>=0:_check(_method(dialog,12,ctypes.c_void_p)(dialog,folder),'设置初始文件夹')
        # No cross-process browser owner: it can block activation on a worker thread.
        result=_method(dialog,3,wintypes.HWND)(dialog,None)
        if result&0xffffffff!=0x800704c7:
            _check(result,'显示目录选择器')
            _check(_method(dialog,20,ctypes.POINTER(ctypes.c_void_p))(dialog,ctypes.byref(item)),'获取所选目录')
            _check(_method(item,5,ctypes.c_uint,ctypes.POINTER(ctypes.c_void_p))(item,0x80058000,ctypes.byref(text)),'获取目录路径')
            selected=ctypes.wstring_at(text)
    finally:
        if text:ole.CoTaskMemFree(text)
        for pointer in (item,folder,dialog):
            if pointer:_method(pointer,2)(pointer)
        ole.CoUninitialize()
    return selected

def choose_folder(project_root,initial=''):
    if os.name!='nt':raise ValueError('当前系统尚未接入文件夹选择窗口')
    if not isinstance(initial,str):raise ValueError('Invalid initial folder')
    if not _DIALOG_LOCK.acquire(blocking=False):raise ValueError('文件夹选择窗口已经打开，请先完成选择')
    try:
        folder=Path(initial.strip()) if initial.strip() else Path(project_root)
        if not folder.is_absolute():folder=Path(project_root)/folder
        folder=folder.resolve()
        while not folder.is_dir() and folder!=folder.parent:folder=folder.parent
        selected=_browse(str(folder))
        if selected is not None and (not isinstance(selected,str) or not Path(selected).is_dir()):raise ValueError('所选文件夹不存在')
        return {'path':selected,'cancelled':selected is None}
    finally:_DIALOG_LOCK.release()
