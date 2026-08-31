namespace Avacom.Student.PlatformServices;

public interface IKioskService
{
    /// <summary>
    /// Indica si el dispositivo tiene el bloqueo real del sistema operativo
    /// aprovisionado (Device Owner en Android, Assigned Access en Windows).
    /// </summary>
    bool IsTrueDeviceLockAvailable { get; }

    /// <summary>
    /// Ocupa toda la pantalla sin bordes ni barras, desde el arranque de la
    /// aplicación y antes de que exista un examen. Es el equivalente al modo de
    /// pantalla completa de un videojuego, no una ventana maximizada.
    /// </summary>
    Task EnterFullScreenAsync(CancellationToken cancellationToken = default);

    Task StartExamLockAsync(CancellationToken cancellationToken = default);
    Task StopExamLockAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Resumen legible de qué restricciones están activas ahora mismo. Se muestra en la
    /// pantalla del examen: sin esto no hay forma de distinguir «el bloqueo falló» de
    /// «el bloqueo está puesto pero Ctrl+Alt+Supr no se puede cerrar».
    /// </summary>
    string LockdownSummary { get; }
}

public interface IEmergencyRecoveryService
{
    bool ValidatePin(string pin);
    void ChangePin(string currentPin, string newPin);
}
