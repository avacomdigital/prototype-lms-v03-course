// Android.App es imprescindible: sin él, IntentFilter se resolvía a
// Android.Content.IntentFilter —una clase, no un atributo— y MetaData no existía.
// Los atributos de generación de manifiesto viven todos en Android.App.
using Android.App;
using Android.App.Admin;
using Android.Content;

namespace Avacom.Student;

[BroadcastReceiver(Name = "com.avacom.student.ExamDeviceAdminReceiver", Permission = "android.permission.BIND_DEVICE_ADMIN", Exported = true)]
[IntentFilter(["android.app.action.DEVICE_ADMIN_ENABLED", "android.app.action.PROFILE_PROVISIONING_COMPLETE"])]
[MetaData("android.app.device_admin", Resource = "@xml/device_admin_receiver")]
public sealed class ExamDeviceAdminReceiver : DeviceAdminReceiver
{
    public override void OnEnabled(Context context, Intent intent) => Android.Util.Log.Info("AVACOM-KIOSK", "Device admin enabled");
    public override void OnDisabled(Context context, Intent intent) => Android.Util.Log.Warn("AVACOM-KIOSK", "Device admin disabled");
}

