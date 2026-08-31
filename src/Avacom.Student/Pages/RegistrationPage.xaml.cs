using Avacom.Student.ViewModels;

namespace Avacom.Student.Pages;

public partial class RegistrationPage : ContentPage
{
    public RegistrationPage(RegistrationViewModel viewModel)
    {
        InitializeComponent();
        BindingContext = viewModel;
    }
}

