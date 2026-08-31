using Avacom.OPS.Core.Services;
using Avacom.OPS.Master.Services;
using Microsoft.Extensions.DependencyInjection;

namespace Avacom.OPS.Master;

public partial class App : Application
{
    private readonly IServiceProvider _services;

    public App(IServiceProvider services)
    {
        InitializeComponent();
        _services = services;
    }

    // La página se resuelve aquí, no en el constructor. Si se inyectara
    // DashboardPage en el constructor de App, el contenedor la construiría —y
    // parsearía su XAML— antes de que InitializeComponent() cargue los recursos
    // de App.xaml, y el {StaticResource PageGradient} de la página no existiría
    // todavía: la aplicación se cerraba al arrancar.
    // CreateWindow corre después de InitializeComponent, así que los recursos ya están.
    protected override Window CreateWindow(IActivationState? activationState)
    {
        // El título hay que ponerlo explícitamente: al asignar MainPage lo tomaba
        // de ApplicationTitle, pero una Window creada a mano nace sin título.
        var window = new Window(_services.GetRequiredService<DashboardPage>()) { Title = "AVACOM OPS Master" };

        // La API se levanta desde aquí para que abrir el .exe directamente funcione,
        // sin depender de que alguien use el acceso directo al .bat. Se hace en
        // Created y no en el constructor: si tardara, la ventana ni aparecería y el
        // profesor vería un icono que no abre nada.
        window.Created += async (_, _) =>
        {
            var host = _services.GetRequiredService<LocalApiHost>();
            try
            {
                await host.EnsureRunningAsync();
            }
            catch (Exception exception)
            {
                // Que la API no arranque no debe impedir abrir el panel: el
                // indicador queda en rojo y explica el estado.
                await _services.GetRequiredService<ILocalLog>()
                    .WriteAsync("api-host", "EnsureRunning lanzó", exception);
            }
        };

        // Destroying y no Closing: se dispara cuando la ventana se está cerrando de
        // verdad, así que la API no se queda huérfana ocupando el puerto 8000.
        window.Destroying += async (_, _) =>
            await _services.GetRequiredService<LocalApiHost>().DisposeAsync();

        return window;
    }
}
