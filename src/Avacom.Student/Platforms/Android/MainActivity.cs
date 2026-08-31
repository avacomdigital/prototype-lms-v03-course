using Android.App;
using Android.Content.PM;
using Android.OS;
using Avacom.Student.Services;
using Microsoft.Extensions.DependencyInjection;

namespace Avacom.Student;

[Activity(
    Theme = "@style/Maui.SplashTheme",
    MainLauncher = true,
    LaunchMode = LaunchMode.SingleTask,
    ScreenOrientation = ScreenOrientation.SensorLandscape,
    ConfigurationChanges = ConfigChanges.ScreenSize | ConfigChanges.Orientation | ConfigChanges.UiMode | ConfigChanges.ScreenLayout | ConfigChanges.SmallestScreenSize | ConfigChanges.Density,
    Exported = true)]
public class MainActivity : MauiAppCompatActivity
{
    protected override void OnCreate(Bundle? savedInstanceState)
    {
        base.OnCreate(savedInstanceState);
        Window?.AddFlags(Android.Views.WindowManagerFlags.KeepScreenOn);
        HideSystemUi();
    }

    public override void OnWindowFocusChanged(bool hasFocus)
    {
        base.OnWindowFocusChanged(hasFocus);
        if (hasFocus) HideSystemUi();
    }

    /// <summary>
    /// Ignora el botón Atrás mientras el examen está en curso. Con Device Owner el Lock
    /// Task ya lo bloquea; esto cubre además los dispositivos sin aprovisionar, donde el
    /// Atrás sacaría al estudiante del examen a medias.
    /// </summary>
#pragma warning disable CS0612 // Compatibilidad desde Android API 26.
    public override void OnBackPressed()
    {
        if (IsExamInProgress())
        {
            HideSystemUi();
            return;
        }
        base.OnBackPressed();
    }
#pragma warning restore CS0612

    private static bool IsExamInProgress()
    {
        var session = IPlatformApplication.Current?.Services.GetService<ExamSession>();
        return session?.IsExamInProgress == true;
    }

    public void HideSystemUi()
    {
        // OperatingSystem.IsAndroidVersionAtLeast en lugar de comparar Build.VERSION:
        // el analizador de compatibilidad reconoce esta forma y deja de advertir por
        // cada uso de InsetsController, que sólo existe desde Android 11 (API 30).
        if (OperatingSystem.IsAndroidVersionAtLeast(30))
        {
            var controller = Window?.InsetsController;
            if (controller is null) return;
            controller.Hide(Android.Views.WindowInsets.Type.StatusBars() | Android.Views.WindowInsets.Type.NavigationBars());
            controller.SystemBarsBehavior = (int)Android.Views.WindowInsetsControllerBehavior.ShowTransientBarsBySwipe;
            return;
        }

        // La asignación no puede ir sobre `Window?.DecorView.X`: eso es una asignación
        // condicional nula, que en C# sigue siendo función en vista previa y no compila.
        var decorView = Window?.DecorView;
        if (decorView is null) return;
#pragma warning disable CS0618
        decorView.SystemUiVisibility = (Android.Views.StatusBarVisibility)(
            Android.Views.SystemUiFlags.ImmersiveSticky |
            Android.Views.SystemUiFlags.Fullscreen |
            Android.Views.SystemUiFlags.HideNavigation |
            Android.Views.SystemUiFlags.LayoutStable |
            Android.Views.SystemUiFlags.LayoutFullscreen |
            Android.Views.SystemUiFlags.LayoutHideNavigation);
#pragma warning restore CS0618
    }
}
