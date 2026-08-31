using Avacom.OPS.Core.Services;
using Avacom.Student.Pages;
using Avacom.Student.PlatformServices;
using Avacom.Student.Services;
using Avacom.Student.ViewModels;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Avacom.Student;

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
        builder.Services.AddSingleton<ClientEndpointSettings>();
        // La BaseAddress de marcador es obligatoria: sin ella HttpClient rechaza las
        // rutas relativas antes de llegar al handler. Ver EndpointRewritingHandler.
        builder.Services.AddHttpClient<ILmsApiClient, LmsApiClient>(
                client => client.BaseAddress = EndpointRewritingHandler.PlaceholderBaseAddress)
            .AddHttpMessageHandler(services =>
                new EndpointRewritingHandler(() => services.GetRequiredService<ClientEndpointSettings>().Current));
        builder.Services.AddTransient<ILmsRealtimeClient, LmsRealtimeClient>();
        builder.Services.AddSingleton<ILocalLog>(_ => new FileLocalLog(Path.Combine(FileSystem.AppDataDirectory, "logs", "student.log")));
        builder.Services.AddSingleton<ExamSession>();
        builder.Services.AddSingleton<IEmergencyRecoveryService, EmergencyRecoveryService>();
#if ANDROID
        builder.Services.AddSingleton<IKioskService, Platforms.Android.AndroidKioskService>();
#elif WINDOWS
        builder.Services.AddSingleton<IKioskService, Platforms.Windows.WindowsKioskService>();
#endif
        builder.Services.AddSingleton<AppShell>();
        builder.Services.AddTransient<RegistrationViewModel>();
        builder.Services.AddTransient<CoursesViewModel>();
        builder.Services.AddTransient<CourseDetailViewModel>();
        builder.Services.AddTransient<ExamViewModel>();
        builder.Services.AddTransient<FinishedViewModel>();
        builder.Services.AddTransient<RegistrationPage>();
        builder.Services.AddTransient<CoursesPage>();
        builder.Services.AddTransient<CourseDetailPage>();
        builder.Services.AddTransient<ExamPage>();
        builder.Services.AddTransient<FinishedPage>();
        return builder.Build();
    }
}
