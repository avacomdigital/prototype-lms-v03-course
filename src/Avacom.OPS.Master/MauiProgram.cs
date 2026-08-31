using Avacom.OPS.Core.Services;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Avacom.OPS.Master;

public static class MauiProgram
{
    public static MauiApp CreateMauiApp()
    {
        var builder = MauiApp.CreateBuilder()
            .UseMauiApp<App>()
            .ConfigureFonts(fonts =>
            {
                fonts.AddFont("Geist-Regular.ttf", "Geist");
                fonts.AddFont("Geist-Bold.ttf", "GeistBold");
            });
#if DEBUG
        builder.Logging.AddDebug();
#endif
        builder.Services.AddSingleton<MasterEndpointSettings>();
        // La BaseAddress de marcador es obligatoria: sin ella HttpClient rechaza las
        // rutas relativas antes de llegar al handler. Ver EndpointRewritingHandler.
        builder.Services.AddHttpClient<ILmsApiClient, LmsApiClient>(
                client => client.BaseAddress = EndpointRewritingHandler.PlaceholderBaseAddress)
            .AddHttpMessageHandler(services =>
                new EndpointRewritingHandler(() => services.GetRequiredService<MasterEndpointSettings>().Current));
        builder.Services.AddTransient<ILmsRealtimeClient, LmsRealtimeClient>();
        builder.Services.AddSingleton<ILocalLog>(_ => new FileLocalLog(Path.Combine(FileSystem.AppDataDirectory, "logs", "master.log")));
        // Singleton: representa un único proceso de API, y dos instancias
        // intentarían enlazar el mismo puerto 8000.
        builder.Services.AddSingleton<Services.LocalApiHost>();
        builder.Services.AddSingleton<Services.ApiDiagnostics>();
        // Abrir un archivo es capacidad de la plataforma: el ViewModel solo ve la interfaz.
        builder.Services.AddSingleton<Services.IPackageFileSource, Services.MauiPackageFileSource>();
        builder.Services.AddSingleton<DashboardViewModel>();
        builder.Services.AddSingleton<DashboardPage>();
        return builder.Build();
    }
}
