using System.Security.Cryptography;
using System.Text;
using Avacom.Student.PlatformServices;

namespace Avacom.Student.Services;

public sealed class EmergencyRecoveryService : IEmergencyRecoveryService
{
    private const string PinHashKey = "emergency_pin_sha256";
    private const string PrototypeDefaultPin = "482617";

    public bool ValidatePin(string pin) => CryptographicOperations.FixedTimeEquals(Hash(pin), GetHash());

    public void ChangePin(string currentPin, string newPin)
    {
        if (!ValidatePin(currentPin)) throw new UnauthorizedAccessException("PIN actual incorrecto.");
        if (newPin.Length < 6 || !newPin.All(char.IsDigit)) throw new ArgumentException("El PIN debe tener al menos seis dígitos.");
        Preferences.Default.Set(PinHashKey, Convert.ToHexString(Hash(newPin)));
    }

    private static byte[] Hash(string value) => SHA256.HashData(Encoding.UTF8.GetBytes(value));
    private static byte[] GetHash()
    {
        var stored = Preferences.Default.Get(PinHashKey, "");
        return string.IsNullOrWhiteSpace(stored) ? Hash(PrototypeDefaultPin) : Convert.FromHexString(stored);
    }
}

