from django.core.management.base import BaseCommand
from apps.settings.models import SystemSetting

class Command(BaseCommand):
    help = 'Seed default system settings'
    
    def handle(self, *args, **options):
        self.stdout.write('Seeding system settings...')
        
        settings_data = [
            # System Settings
            {
                'key': 'SYSTEM_NAME',
                'value': 'RonoSystems',
                'setting_type': 'text',
                'category': 'system',
                'label': 'System Name',
                'description': 'Name of the system displayed throughout the application',
                'is_editable': True
            },
            {
                'key': 'SYSTEM_STATUS',
                'value': 'online',
                'setting_type': 'text',
                'category': 'system',
                'label': 'System Status',
                'description': 'System status (online, maintenance, offline)',
                'is_editable': True
            },
            {
                'key': 'MAINTENANCE_MODE',
                'value': 'false',
                'setting_type': 'boolean',
                'category': 'system',
                'label': 'Maintenance Mode',
                'description': 'Enable maintenance mode to restrict access',
                'is_editable': True
            },
            {
                'key': 'MAINTENANCE_MESSAGE',
                'value': 'System is currently undergoing maintenance. Please check back later.',
                'setting_type': 'text',
                'category': 'system',
                'label': 'Maintenance Message',
                'description': 'Message shown to users during maintenance',
                'is_editable': True
            },
            
            # Email Settings
            {
                'key': 'EMAIL_HOST',
                'value': 'smtp.gmail.com',
                'setting_type': 'text',
                'category': 'email',
                'label': 'SMTP Host',
                'description': 'SMTP server hostname',
                'is_editable': True
            },
            {
                'key': 'EMAIL_PORT',
                'value': '587',
                'setting_type': 'integer',
                'category': 'email',
                'label': 'SMTP Port',
                'description': 'SMTP server port',
                'is_editable': True
            },
            {
                'key': 'EMAIL_HOST_USER',
                'value': '',
                'setting_type': 'email',
                'category': 'email',
                'label': 'SMTP Username',
                'description': 'Email address for SMTP authentication',
                'is_editable': True
            },
            {
                'key': 'EMAIL_HOST_PASSWORD',
                'value': '',
                'setting_type': 'text',
                'category': 'email',
                'label': 'SMTP Password',
                'description': 'Password for SMTP authentication',
                'is_editable': True
            },
            {
                'key': 'EMAIL_USE_TLS',
                'value': 'true',
                'setting_type': 'boolean',
                'category': 'email',
                'label': 'Use TLS',
                'description': 'Enable TLS for email sending',
                'is_editable': True
            },
            {
                'key': 'DEFAULT_FROM_EMAIL',
                'value': 'noreply@ronosystems.com',
                'setting_type': 'email',
                'category': 'email',
                'label': 'Default From Email',
                'description': 'Default sender email address',
                'is_editable': True
            },
            
            # Domain Settings
            {
                'key': 'SITE_DOMAIN',
                'value': 'localhost:8000',
                'setting_type': 'url',
                'category': 'domain',
                'label': 'Site Domain',
                'description': 'Primary domain for the application',
                'is_editable': True
            },
            {
                'key': 'SITE_URL',
                'value': 'http://localhost:8000',
                'setting_type': 'url',
                'category': 'domain',
                'label': 'Site URL',
                'description': 'Full URL of the application',
                'is_editable': True
            },
            {
                'key': 'SITE_PROTOCOL',
                'value': 'http',
                'setting_type': 'text',
                'category': 'domain',
                'label': 'Site Protocol',
                'description': 'Protocol used (http or https)',
                'is_editable': True
            },
            
            # Payment Settings
            {
                'key': 'PAYMENT_GATEWAY',
                'value': 'stripe',
                'setting_type': 'text',
                'category': 'payment',
                'label': 'Payment Gateway',
                'description': 'Payment gateway to use (stripe, razorpay, paypal)',
                'is_editable': True
            },
            {
                'key': 'STRIPE_PUBLIC_KEY',
                'value': '',
                'setting_type': 'text',
                'category': 'payment',
                'label': 'Stripe Public Key',
                'description': 'Stripe publishable key',
                'is_editable': True
            },
            {
                'key': 'STRIPE_SECRET_KEY',
                'value': '',
                'setting_type': 'text',
                'category': 'payment',
                'label': 'Stripe Secret Key',
                'description': 'Stripe secret key',
                'is_editable': True
            },
            {
                'key': 'RAZORPAY_KEY_ID',
                'value': '',
                'setting_type': 'text',
                'category': 'payment',
                'label': 'Razorpay Key ID',
                'description': 'Razorpay key ID',
                'is_editable': True
            },
            {
                'key': 'RAZORPAY_KEY_SECRET',
                'value': '',
                'setting_type': 'text',
                'category': 'payment',
                'label': 'Razorpay Key Secret',
                'description': 'Razorpay key secret',
                'is_editable': True
            },
            {
                'key': 'CURRENCY',
                'value': 'KES',
                'setting_type': 'text',
                'category': 'payment',
                'label': 'Currency',
                'description': 'Default currency for payments',
                'is_editable': True
            },
            
            # Branding Settings
            {
                'key': 'SITE_LOGO',
                'value': '',
                'setting_type': 'image',
                'category': 'branding',
                'label': 'Site Logo',
                'description': 'Logo image for the application',
                'is_editable': True
            },
            {
                'key': 'FAVICON',
                'value': '',
                'setting_type': 'image',
                'category': 'branding',
                'label': 'Favicon',
                'description': 'Favicon for the application',
                'is_editable': True
            },
            {
                'key': 'PRIMARY_COLOR',
                'value': '#036a77',
                'setting_type': 'text',
                'category': 'branding',
                'label': 'Primary Color',
                'description': 'Primary brand color',
                'is_editable': True
            },
            {
                'key': 'SECONDARY_COLOR',
                'value': '#2500fa',
                'setting_type': 'text',
                'category': 'branding',
                'label': 'Secondary Color',
                'description': 'Secondary brand color',
                'is_editable': True
            },
        ]
        
        created_count = 0
        updated_count = 0
        
        for setting_data in settings_data:
            setting, created = SystemSetting.objects.get_or_create(
                key=setting_data['key'],
                defaults=setting_data
            )
            if not created:
                for key, value in setting_data.items():
                    setattr(setting, key, value)
                setting.save()
                updated_count += 1
            else:
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} and updated {updated_count} settings')
        )
        
        # Print all settings
        all_settings = SystemSetting.objects.all()
        self.stdout.write('\nSettings in database:')
        for s in all_settings:
            self.stdout.write(f'  - {s.key}: {s.value[:50]} ({s.category})')
