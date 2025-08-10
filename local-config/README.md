# Local Configuration

This directory contains organization-specific configurations and templates that should not be committed to version control.

## Files in this directory:

### Templates
- `templates/donor_acknowledgment_email.html` - Organization-specific HTML email template with letterhead and custom styling
- `templates/SWCA-letterhead-v3-1024x224.png` - Organization letterhead image for email embedding

### Static Assets  
- `static/swca-logo.png` - Organization logo for web interface

### Configuration Files
- `donor-ack.txt` - Organization-specific donation acknowledgment text template
- `Caddyfile` - Production SSL/domain configuration

## Setup Instructions

1. Copy your organization's specific files to this directory structure
2. Update the generic files in the main project with your organization's information
3. The application will automatically prefer local-config files when available

## Environment Variables

Make sure to set these organization-specific environment variables in your `.env` file:
- `ORGANIZATION_NAME` - Your organization's full name
- `ORGANIZATION_LOGO` - URL or path to your logo
- `ORGANIZATION_WEBSITE` - Your organization's website
- `NOTIFICATION_EMAIL` - Email for notifications
- `DOMAIN_NAME` - Your production domain
- `FROM_EMAIL` - Sender email address

See `env-template` for a complete list of configuration options.