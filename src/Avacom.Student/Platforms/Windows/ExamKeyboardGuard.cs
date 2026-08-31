using System.Runtime.InteropServices;

namespace Avacom.Student.Platforms.Windows;

/// <summary>
/// Descarta los atajos con los que un estudiante saldría del examen: tecla Windows,
/// Alt+Tab, Alt+Esc, Ctrl+Esc, Esc, Alt+F4, F11 y el Administrador de tareas por
/// Ctrl+Shift+Esc.
/// </summary>
/// <remarks>
/// <para>
/// Usa un gancho de teclado de bajo nivel (WH_KEYBOARD_LL), la misma técnica de los
/// navegadores de examen comerciales. Funciona sin permisos de administrador y sólo
/// mientras el examen está en curso.
/// </para>
/// <para>
/// Hay un límite que ninguna aplicación puede sortear: <b>Ctrl+Alt+Supr</b>. Windows lo
/// procesa en un escritorio seguro al que los ganchos no llegan, por diseño. Desde ahí
/// se puede abrir el Administrador de tareas o cambiar de usuario. Cerrar esa puerta
/// exige Assigned Access, que es una política de la cuenta, no del proceso.
/// </para>
/// </remarks>
internal static class ExamKeyboardGuard
{
    private const int WhKeyboardLowLevel = 13;
    private const int HcAction = 0;
    private const int WmKeyDown = 0x0100;
    private const int WmKeyUp = 0x0101;
    private const int WmSysKeyDown = 0x0104;
    private const int WmSysKeyUp = 0x0105;

    private const int VkTab = 0x09;
    private const int VkEscape = 0x1B;
    private const int VkF4 = 0x73;
    private const int VkF11 = 0x7A;
    private const int VkLeftWindows = 0x5B;
    private const int VkRightWindows = 0x5C;
    private const int VkShift = 0x10;
    private const int VkControl = 0x11;
    private const int VkAlt = 0x12;

    // El delegado se guarda en un campo estático a propósito: si sólo viviera como
    // argumento, el recolector podría liberarlo y Windows llamaría a memoria inválida.
    private static HookProc? _callback;
    private static IntPtr _hook = IntPtr.Zero;

    internal static bool IsActive => _hook != IntPtr.Zero;

    /// <summary>Instala el gancho. Debe llamarse desde el hilo de interfaz, que tiene bucle de mensajes.</summary>
    internal static void Install()
    {
        if (IsActive) return;
        _callback = OnKey;
        using var module = System.Diagnostics.Process.GetCurrentProcess().MainModule;
        _hook = SetWindowsHookEx(WhKeyboardLowLevel, _callback, GetModuleHandle(module?.ModuleName), 0);
        if (_hook == IntPtr.Zero)
            throw new InvalidOperationException(
                $"No se pudo instalar el bloqueo de teclado (error {Marshal.GetLastWin32Error()}).");
    }

    internal static void Remove()
    {
        if (!IsActive) return;
        UnhookWindowsHookEx(_hook);
        _hook = IntPtr.Zero;
        _callback = null;
    }

    private static IntPtr OnKey(int code, IntPtr wParam, IntPtr lParam)
    {
        // Hay que descartar también el KEYUP, no sólo el KEYDOWN: el menú Inicio se abre
        // al SOLTAR la tecla Windows, así que bloquear sólo la pulsación dejaba pasar el
        // evento que realmente lo dispara. Verificado con un banco de pruebas aislado.
        if (code == HcAction && (wParam == WmKeyDown || wParam == WmSysKeyDown
                                 || wParam == WmKeyUp || wParam == WmSysKeyUp))
        {
            var info = Marshal.PtrToStructure<KeyboardHookStruct>(lParam);
            if (ShouldSwallow((int)info.VirtualKeyCode))
                return 1; // Consumida: no llega a Windows ni a la aplicación.
        }
        return CallNextHookEx(_hook, code, wParam, lParam);
    }

    private static bool ShouldSwallow(int key)
    {
        var alt = IsDown(VkAlt);
        var control = IsDown(VkControl);
        var shift = IsDown(VkShift);

        return key switch
        {
            VkLeftWindows or VkRightWindows => true,          // menú Inicio y todos los Win+…
            VkTab when alt => true,                            // Alt+Tab y Alt+Shift+Tab
            VkEscape => true,                                  // Esc, Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc
            VkF4 when alt => true,                             // Alt+F4
            VkF11 => true,                                     // salir de pantalla completa
            _ => false,
        } || (control && shift && key == VkEscape);            // Administrador de tareas
    }

    private static bool IsDown(int key) => (GetAsyncKeyState(key) & 0x8000) != 0;

    private delegate IntPtr HookProc(int code, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    private struct KeyboardHookStruct
    {
        public uint VirtualKeyCode;
        public uint ScanCode;
        public uint Flags;
        public uint Time;
        public IntPtr ExtraInfo;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, HookProc callback, IntPtr module, uint threadId);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnhookWindowsHookEx(IntPtr hook);

    [DllImport("user32.dll")]
    private static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string? moduleName);

    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int key);
}
