using Android.App;
using Android.App.Admin;
using Android.Content;
using Avacom.Student.PlatformServices;
using Avacom.Student.Services;

namespace Avacom.Student.Platforms.Android;

public sealed class AndroidKioskService(ExamSession session) : IKioskService
{
    private static MainActivity Activity => Platform.CurrentActivity as MainActivity
        ?? throw new InvalidOperationException("La actividad Android no está disponible.");

    private static DevicePolicyManager PolicyManager =>
        (DevicePolicyManager)(Activity.GetSystemService(Context.DevicePolicyService)
        ?? throw new InvalidOperationException("DevicePolicyManager no está disponible."));

    private static ComponentName AdminComponent => new(Activity, Java.Lang.Class.FromType(typeof(ExamDeviceAdminReceiver)));

    public bool IsTrueDeviceLockAvailable => PolicyManager.IsDeviceOwnerApp(Activity.PackageName);

    public string LockdownSummary => IsTrueDeviceLockAvailable
        ? "Device Owner activo · Lock Task bloquea inicio, recientes y notificaciones"
        : "SIN Device Owner: pantalla completa e inmersiva, pero el sistema no está bloqueado";

    /// <summary>
    /// Modo inmersivo desde el arranque: sin barra de estado ni de navegación, antes de
    /// que exista un examen y sin depender de Device Owner.
    /// </summary>
    public Task EnterFullScreenAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return RunOnUiThreadAsync(() => Activity.HideSystemUi());
    }

    public Task StartExamLockAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        session.IsExamInProgress = true;
        return RunOnUiThreadAsync(() =>
        {
            if (!IsTrueDeviceLockAvailable)
            {
                // El prototipo también debe poder probarse en un teléfono común.
                // Sin Device Owner se conserva pantalla completa y el bloqueo de
                // Atrás de MainActivity, aunque Android no permita Lock Task real.
                Activity.HideSystemUi();
                return;
            }
            PolicyManager.SetLockTaskPackages(AdminComponent, [Activity.PackageName!]);
            if (!PolicyManager.IsLockTaskPermitted(Activity.PackageName))
                throw new InvalidOperationException("El paquete no quedó autorizado para Lock Task.");
            if (OperatingSystem.IsAndroidVersionAtLeast(28))
                PolicyManager.SetLockTaskFeatures(AdminComponent, LockTaskFeatures.None);
            PolicyManager.AddUserRestriction(AdminComponent, global::Android.OS.UserManager.DisallowCreateWindows);
            Activity.StartLockTask();
            Activity.HideSystemUi();
        });
    }

    public Task StopExamLockAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        session.IsExamInProgress = false;
        return RunOnUiThreadAsync(() =>
        {
            try { Activity.StopLockTask(); }
            catch (InvalidOperationException) { }
            if (IsTrueDeviceLockAvailable)
                PolicyManager.ClearUserRestriction(AdminComponent, global::Android.OS.UserManager.DisallowCreateWindows);
        });
    }

    /// <summary>
    /// Ejecuta la política en el hilo de interfaz de Android y devuelve el resultado
    /// al llamador. Sin este puente, una excepción lanzada dentro de RunOnUiThread
    /// (por ejemplo, un dispositivo que no quedó como Device Owner) no la vería el
    /// try/catch del ViewModel: subiría por el hilo de interfaz y cerraría la app en
    /// plena presentación del examen.
    /// </summary>
    private static Task RunOnUiThreadAsync(Action policy)
    {
        var activity = Activity;
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        activity.RunOnUiThread(() =>
        {
            try
            {
                policy();
                completion.TrySetResult();
            }
            catch (Exception exception)
            {
                completion.TrySetException(exception);
            }
        });
        return completion.Task;
    }
}
