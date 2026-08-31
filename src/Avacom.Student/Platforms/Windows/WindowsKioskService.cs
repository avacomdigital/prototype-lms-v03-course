using Avacom.Student.PlatformServices;
using Avacom.Student.Services;
using Microsoft.UI.Windowing;
using WinRT.Interop;

namespace Avacom.Student.Platforms.Windows;

/// <summary>
/// Pantalla completa y bloqueo de salida en Windows.
/// </summary>
/// <remarks>
/// El bloqueo verdaderamente inviolable en Windows es una propiedad persistente de la
/// cuenta de usuario (Assigned Access / Shell Launcher), no algo que una aplicación
/// pueda imponerse a sí misma: Alt+Tab, la tecla Windows y Ctrl+Alt+Supr los gobierna
/// el sistema operativo. Lo que sí hace esta clase, y sirve incluso en un equipo sin
/// aprovisionar: ocupar toda la pantalla sin bordes desde el arranque y rechazar el
/// cierre de la ventana mientras el examen está en curso.
/// </remarks>
public sealed class WindowsKioskService(ExamSession session) : IKioskService
{
    /// <summary>
    /// Interruptor sólo para desarrollo: <c>AVACOM_QUIZ_NO_LOCKDOWN=1</c> mantiene la
    /// pantalla completa pero no instala el bloqueo de teclado, ni cubre los monitores
    /// extra, ni impide cerrar la ventana.
    /// </summary>
    /// <remarks>
    /// Existe porque el gancho de teclado es de ámbito global: al probar el panel del
    /// profesor y el examen en el mismo equipo, Alt+Tab queda descartado y no habría
    /// forma de volver al Master para finalizar el examen. En los dispositivos de la
    /// sede esta variable no se define, así que el bloqueo se aplica completo.
    /// </remarks>
    private static bool LockdownDisabled =>
        Environment.GetEnvironmentVariable("AVACOM_QUIZ_NO_LOCKDOWN") == "1";

    private bool _closeHandlerAttached;

    public bool IsTrueDeviceLockAvailable => File.Exists(Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AVACOM", "kiosk-provisioned.marker"));

    public string LockdownSummary
    {
        get
        {
            if (LockdownDisabled) return "modo desarrollo: sin bloqueo (AVACOM_QUIZ_NO_LOCKDOWN=1)";
            var partes = new List<string>
            {
                ExamKeyboardGuard.IsActive ? "teclado bloqueado" : "TECLADO SIN BLOQUEAR",
            };
            if (SecondaryScreenBlocker.ActiveCount > 0)
                partes.Add($"{SecondaryScreenBlocker.ActiveCount} pantalla(s) extra cubierta(s)");
            partes.Add(IsTrueDeviceLockAvailable ? "Assigned Access activo" : "sin Assigned Access (Ctrl+Alt+Supr libre)");
            return string.Join(" · ", partes);
        }
    }

    public Task EnterFullScreenAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return OnMainThreadAsync(appWindow =>
        {
            AttachCloseGuard(appWindow);
            // FullScreen es el modo exclusivo: sin borde, sin barra de título y por
            // encima de la barra de tareas. Maximizar dejaba ambas visibles.
            if (appWindow.Presenter.Kind != AppWindowPresenterKind.FullScreen)
                appWindow.SetPresenter(AppWindowPresenterKind.FullScreen);
        });
    }

    public async Task StartExamLockAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        // Se marca antes de avisar de la falta de aprovisionamiento: el rechazo al
        // cierre debe aplicar también en un equipo sin Assigned Access.
        session.IsExamInProgress = true;
        await EnterFullScreenAsync(cancellationToken);
        if (LockdownDisabled)
        {
            throw new InvalidOperationException(
                "AVACOM_QUIZ_NO_LOCKDOWN=1: modo desarrollo. Pantalla completa activa, pero sin bloqueo de " +
                "teclado, sin cubrir monitores extra y con el cierre permitido. No usar en un examen real.");
        }

        await OnMainThreadAsync(_ =>
        {
            ExamKeyboardGuard.Install();
            SecondaryScreenBlocker.Cover();
        });

        if (!IsTrueDeviceLockAvailable)
            throw new InvalidOperationException(
                "Assigned Access no está aprovisionado. La aplicación ocupa todas las pantallas, no se puede " +
                "cerrar y descarta la tecla Windows, Alt+Tab, Alt+Esc y Esc; pero Ctrl+Alt+Supr sigue " +
                "disponible porque Windows lo atiende en un escritorio seguro. Ejecuta " +
                "scripts/windows/Install-Kiosk.ps1 como administrador para cerrar también esa vía.");
    }

    public Task StopExamLockAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        // Se libera el cierre y los atajos, pero la ventana sigue en pantalla completa:
        // el examen terminó y el estudiante sale con el botón "Cerrar" de la pantalla final.
        session.IsExamInProgress = false;
        return OnMainThreadAsync(_ =>
        {
            ExamKeyboardGuard.Remove();
            SecondaryScreenBlocker.Uncover();
        });
    }

    /// <summary>
    /// Rechaza el cierre de la ventana mientras el examen está en curso. Cubre la
    /// combinación Alt+F4 y cualquier cierre programático.
    /// </summary>
    private void AttachCloseGuard(AppWindow appWindow)
    {
        if (_closeHandlerAttached) return;
        _closeHandlerAttached = true;
        appWindow.Closing += (_, args) =>
        {
            if (session.IsExamInProgress && !LockdownDisabled) args.Cancel = true;
        };
    }

    private static Task OnMainThreadAsync(Action<AppWindow> action)
    {
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        MainThread.BeginInvokeOnMainThread(() =>
        {
            try
            {
                var appWindow = ResolveAppWindow();
                if (appWindow is null)
                    throw new InvalidOperationException("La ventana nativa aún no está disponible.");
                action(appWindow);
                completion.TrySetResult();
            }
            catch (Exception exception)
            {
                // Sin este puente la excepción subiría por el hilo de interfaz y
                // cerraría la aplicación en vez de llegar al try/catch del ViewModel.
                completion.TrySetException(exception);
            }
        });
        return completion.Task;
    }

    private static AppWindow? ResolveAppWindow()
    {
        var nativeWindow = Application.Current?.Windows.FirstOrDefault()?.Handler?.PlatformView as Microsoft.UI.Xaml.Window;
        if (nativeWindow is null) return null;
        var windowId = Microsoft.UI.Win32Interop.GetWindowIdFromWindow(WindowNative.GetWindowHandle(nativeWindow));
        return AppWindow.GetFromWindowId(windowId);
    }
}
