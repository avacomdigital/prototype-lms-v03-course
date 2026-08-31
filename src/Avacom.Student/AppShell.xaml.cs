using Avacom.Student.Pages;

namespace Avacom.Student;

public partial class AppShell : Shell
{
    public AppShell(RegistrationPage registrationPage)
    {
        InitializeComponent();
        RootContent.Content = registrationPage;
        Routing.RegisterRoute(nameof(CoursesPage), typeof(CoursesPage));
        Routing.RegisterRoute(nameof(CourseDetailPage), typeof(CourseDetailPage));
        Routing.RegisterRoute(nameof(ExamPage), typeof(ExamPage));
        Routing.RegisterRoute(nameof(FinishedPage), typeof(FinishedPage));
    }
}
