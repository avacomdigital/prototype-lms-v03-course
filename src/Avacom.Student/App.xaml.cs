using Avacom.Student.PlatformServices;
using Microsoft.Extensions.DependencyInjection;

namespace Avacom.Student;

public partial class App : Application
{
    private readonly IServiceProvider _services;

    public App(IServiceProvider services)
    {
        InitializeComponent();
        _services = services;
    }

    // El shell se resuelve aquí, no en el constructor. Al inyectar AppShell en el
    // constructor de App, el contenedor lo construía —y con él RegistrationPage y su
    // XAML— antes de que InitializeComponent() cargara los recursos de App.xaml, así
    // que el {StaticResource PageGradient} de la página aún no existía y la aplicación
    // se cerraba al arrancar. CreateWindow corre después, con los recursos ya cargados.
    protected override Window CreateWindow(IActivationState? activationState)
    {
        var window = new Window(_services.GetRequiredService<AppShell>()) { Title = "AVACOM Student" };

        // Pantalla completa desde el arranque, no sólo al iniciar el examen: el
        // estudiante no debe ver el escritorio ni la barra de tareas en ningún momento.
        // Se hace en Created porque antes de ese punto no existe la ventana nativa.
        window.Created += async (_, _) =>
        {
            try
            {
                await _services.GetRequiredService<IKioskService>().EnterFullScreenAsync();
            }
            catch (Exception exception)
            {
                // Que falle la pantalla completa no debe impedir presentar el examen.
                await _services.GetRequiredService<Avacom.OPS.Core.Services.ILocalLog>()
                    .WriteAsync("kiosk", "EnterFullScreen failed", exception);
            }
        };

        return window;
    }
}
