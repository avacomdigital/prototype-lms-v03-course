using Avacom.OPS.Core.Models;

namespace Avacom.Student.ViewModels;

public sealed class AnswerOptionViewModel(QuizOption option) : ViewModelBase
{
    private bool _isSelected;
    public QuizOption Option { get; } = option;
    public string Id => Option.Id;
    public string Text => Option.Text;
    public string Letter => Option.Letter;
    public bool IsSelected { get => _isSelected; set => Set(ref _isSelected, value); }
}
