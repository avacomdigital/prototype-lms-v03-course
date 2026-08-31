using Avacom.Student.ViewModels;

namespace Avacom.Student.Pages;

public partial class FinishedPage : ContentPage
{
    public FinishedPage(FinishedViewModel viewModel)
    {
        InitializeComponent();
        BindingContext = viewModel;
    }
}

