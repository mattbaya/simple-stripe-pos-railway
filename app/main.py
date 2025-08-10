import os
import logging
import smtplib
import json
import base64
import csv
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, jsonify, redirect, url_for
from urllib.parse import urlparse
import stripe
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Explicitly set Stripe API key from environment
stripe_secret_key = os.getenv('STRIPE_SECRET_KEY')
if stripe_secret_key:
    stripe.api_key = stripe_secret_key
else:
    logger.error("STRIPE_SECRET_KEY environment variable not found!")
STRIPE_LOCATION_ID = os.getenv('STRIPE_LOCATION_ID')
# Membership amounts in cents
INDIVIDUAL_MEMBERSHIP_AMOUNT = int(os.getenv('INDIVIDUAL_MEMBERSHIP_AMOUNT', '3500'))  # $35 in cents
HOUSEHOLD_MEMBERSHIP_AMOUNT = int(os.getenv('HOUSEHOLD_MEMBERSHIP_AMOUNT', '5000'))  # $50 in cents

# Email configuration
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
FROM_EMAIL = os.getenv('FROM_EMAIL')
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL')
ORGANIZATION_NAME = os.getenv('ORGANIZATION_NAME', 'Community Organization')
ORGANIZATION_LOGO = os.getenv('ORGANIZATION_LOGO', '/static/logo.png')
ORGANIZATION_WEBSITE = os.getenv('ORGANIZATION_WEBSITE', '')
DOMAIN_NAME = os.getenv('DOMAIN_NAME', '')  # Primary domain (e.g., pos.yourcommunity.org)
EMAIL_HEADER_HTML = os.getenv('EMAIL_HEADER_HTML', '')  # Custom HTML for email headers

# OAuth2 configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REFRESH_TOKEN = os.getenv('GOOGLE_REFRESH_TOKEN')

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Transaction logging directory
LOG_DIR = os.getenv('LOG_DIR', '/app/logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def check_domain_redirect():
    """Check if request should be redirected to primary domain"""
    if not DOMAIN_NAME:
        return None
    
    # Get the host from the request
    host = request.host.lower()
    primary_domain = DOMAIN_NAME.lower()
    
    # Remove port number if present for comparison
    host_without_port = host.split(':')[0]
    primary_without_port = primary_domain.split(':')[0]
    
    # If accessing from wrong domain, redirect
    if host_without_port != primary_without_port and host_without_port != 'localhost':
        redirect_url = f"https://{primary_domain}{request.full_path.rstrip('?')}"
        return redirect(redirect_url, code=301)
    
    # Force HTTPS redirect if not localhost
    if not request.is_secure and host_without_port != 'localhost':
        redirect_url = f"https://{host}{request.full_path.rstrip('?')}"
        return redirect(redirect_url, code=301)
    
    return None

def log_transaction(payment_intent_id, payer_name, payer_email, amount, payment_type, status, metadata=None):
    """Log transaction details (no sensitive payment info)"""
    try:
        log_file = os.path.join(LOG_DIR, f"transactions_{datetime.now().strftime('%Y-%m')}.csv")
        
        # Create CSV headers if file doesn't exist
        file_exists = os.path.isfile(log_file)
        
        with open(log_file, 'a', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'timestamp', 'payment_intent_id', 'payer_name', 'payer_email', 
                'amount_cents', 'amount_dollars', 'payment_type', 'status',
                'cover_fees', 'base_amount', 'fee_amount'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            # Extract metadata
            cover_fees = metadata.get('cover_fees', 'false') if metadata else 'false'
            base_amount = metadata.get('base_amount', str(amount)) if metadata else str(amount)
            fee_amount = metadata.get('fee_amount', '0') if metadata else '0'
            
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                'payment_intent_id': payment_intent_id,
                'payer_name': payer_name,
                'payer_email': payer_email or '',
                'amount_cents': amount,
                'amount_dollars': f"{amount/100:.2f}",
                'payment_type': payment_type,
                'status': status,
                'cover_fees': cover_fees,
                'base_amount': base_amount,
                'fee_amount': fee_amount
            })
            
        logger.info(f"Transaction logged: {payment_intent_id} - ${amount/100:.2f}")
        
    except Exception as e:
        logger.error(f"Error logging transaction: {str(e)}")

@app.before_request
def before_request():
    """Handle domain redirects before processing requests"""
    redirect_response = check_domain_redirect()
    if redirect_response:
        return redirect_response

def get_gmail_credentials():
    """Get valid Gmail credentials using OAuth2"""
    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
        logger.warning("OAuth2 configuration incomplete")
        return None
    
    try:
        # Create credentials from the refresh token
        credentials = Credentials(
            token=None,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=SCOPES
        )
        
        # Refresh the token if needed
        if not credentials.valid:
            credentials.refresh(Request())
        
        return credentials
        
    except Exception as e:
        logger.error(f"Failed to get Gmail credentials: {str(e)}")
        return None

def send_email(to_email, subject, body, is_html=False, attachments=None):
    """Send an email using Gmail API with optional attachments"""
    if not FROM_EMAIL:
        logger.warning("FROM_EMAIL not configured - skipping email send")
        return False
    
    credentials = get_gmail_credentials()
    if not credentials:
        logger.warning("Could not get valid credentials - skipping email send")
        return False
    
    try:
        from googleapiclient.discovery import build
        import email.mime.multipart
        import email.mime.text
        
        # Build Gmail service
        service = build('gmail', 'v1', credentials=credentials)
        
        # Create message
        if attachments:
            msg = email.mime.multipart.MIMEMultipart('related')
        else:
            msg = email.mime.multipart.MIMEMultipart('alternative')
            
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        
        if is_html:
            msg.attach(email.mime.text.MIMEText(body, 'html'))
        else:
            msg.attach(email.mime.text.MIMEText(body, 'plain'))
        
        # Add attachments if provided
        if attachments:
            for attachment in attachments:
                msg.attach(attachment)
        
        # Encode message
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        
        # Send message
        message = service.users().messages().send(
            userId='me', 
            body={'raw': raw_message}
        ).execute()
        
        logger.info(f"Email sent successfully to {to_email} (Message ID: {message['id']})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        return False

def send_receipt_email(payer_email, payer_name, amount, payment_type, transaction_id):
    """Send receipt email to the donor using HTML template with letterhead"""
    if not payer_email:
        return False
    
    amount_dollars = amount / 100
    date_str = datetime.now().strftime('%B %d, %Y')
    
    subject = f"Thank you for your {payment_type} - {ORGANIZATION_NAME}"
    
    # Load the HTML template - prefer local-config version if available
    try:
        local_template_path = os.path.join(os.path.dirname(__file__), '..', 'local-config', 'templates', 'donor_acknowledgment_email.html')
        template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'donor_acknowledgment_email.html')
        
        # Use local-config template if it exists, otherwise use the generic one
        if os.path.exists(local_template_path):
            template_path = local_template_path
            logger.info("Using local-config email template")
        else:
            logger.info("Using generic email template")
            
        with open(template_path, 'r', encoding='utf-8') as f:
            html_template = f.read()
        
        # Prepare template variables based on payment type
        is_membership = payment_type.lower() in ['individual membership', 'household membership']
        
        # Create membership-specific message
        membership_message = ""
        if is_membership:
            membership_message = '''
            <div class="membership-message">
                <strong>New Member Information Request:</strong><br>
                Since you paid for your membership using our mobile card reader, we only collected your name and email address. If you are a new member, first off - <strong>Thank you!</strong> We're honored to have you join us. 
                <br><br>
                We'd appreciate it if you could please <strong>reply to this email with your address and phone number</strong> so we can complete your membership record and keep you updated on community events and activities.
            </div>
            '''
        
        # Set appropriate text based on payment type
        payment_type_title = payment_type.title()
        goods_services_statement = ("No goods or services were provided to you in return for your gift." if not is_membership 
                                  else "Membership benefits are not considered goods or services for tax deduction purposes.")
        
        # Replace template variables
        html_body = html_template.format(
            payer_name=payer_name,
            amount_formatted=f"${amount_dollars:.2f}",
            payment_date=date_str,
            organization_name=ORGANIZATION_NAME,
            payment_intent_id=transaction_id,
            payment_type=payment_type.lower(),
            payment_type_title=payment_type_title,
            membership_message=membership_message,
            goods_services_statement=goods_services_statement
        )
        
        # Prepare letterhead image attachment - prefer local-config version
        attachments = []
        local_letterhead_path = os.path.join(os.path.dirname(__file__), '..', 'local-config', 'templates', 'SWCA-letterhead-v3-1024x224.png')
        letterhead_path = local_letterhead_path if os.path.exists(local_letterhead_path) else None
        
        if letterhead_path and os.path.exists(letterhead_path):
            with open(letterhead_path, 'rb') as f:
                img_data = f.read()
            
            letterhead_img = MIMEImage(img_data)
            letterhead_img.add_header('Content-ID', '<letterhead>')
            letterhead_img.add_header('Content-Disposition', 'inline', filename='letterhead.png')
            attachments.append(letterhead_img)
            logger.info("Using local-config letterhead image")
        else:
            logger.info("No letterhead image found, proceeding without embedded image")
        
        return send_email(payer_email, subject, html_body, is_html=True, attachments=attachments)
        
    except Exception as e:
        logger.error(f"Error loading email template: {str(e)}")
        # Fallback to simple email if template loading fails
        is_membership_fallback = payment_type.lower() in ['individual membership', 'household membership']
        membership_request = ""
        if is_membership_fallback:
            membership_request = f"""
            <div style="background-color: #e8f5e8; padding: 15px; margin: 15px 0; border-left: 4px solid #28a745; border-radius: 5px;">
                <strong>New Member Information Request:</strong><br>
                Since you paid for your membership using our mobile card reader, we only collected your name and email address. If you are a new member, first off - <strong>Thank you!</strong> We're honored to have you join us.
                <br><br>
                We'd appreciate it if you could please <strong>reply to this email with your address and phone number</strong> so we can complete your membership record and keep you updated on community events and activities.
            </div>
            """
        
        fallback_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2>Thank you for your {payment_type}!</h2>
            <p>Dear {payer_name},</p>
            <p>Thank you for your generous {payment_type} of <strong>${amount_dollars:.2f}</strong> to {ORGANIZATION_NAME}.</p>
            <p><strong>Transaction Details:</strong><br>
            Date: {date_str}<br>
            Amount: ${amount_dollars:.2f}<br>
            Transaction ID: {transaction_id}</p>
            {membership_request}
            <p>This serves as your receipt for tax purposes.</p>
            <p>Sincerely,<br>{ORGANIZATION_NAME}</p>
        </body>
        </html>
        """
        return send_email(payer_email, subject, fallback_body, is_html=True)

def calculate_fee_amount(base_amount_cents):
    """Calculate Stripe processing fee (2.9% + $0.30)"""
    fee_percentage = 0.029
    fee_fixed = 30  # 30 cents in cents
    
    # Calculate total fee
    fee = round(base_amount_cents * fee_percentage) + fee_fixed
    return fee

def calculate_total_with_fees(base_amount_cents):
    """Calculate total amount when user opts to cover processing fees"""
    fee = calculate_fee_amount(base_amount_cents)
    return base_amount_cents + fee

def send_notification_email(payer_name, payer_email, amount, payment_type, transaction_id):
    """Send notification email to the organization"""
    amount_dollars = amount / 100
    date_str = datetime.now().strftime('%B %d, %Y at %I:%M %p')
    
    subject = f"New {payment_type} received - ${amount_dollars:.2f}"
    
    body = f"""
New payment received through the POS system:

PAYMENT DETAILS:
- Type: {payment_type.title()}
- Amount: ${amount_dollars:.2f}
- Donor: {payer_name}
- Email: {payer_email or 'Not provided'}
- Date: {date_str}
- Transaction ID: {transaction_id}

This payment was processed through Stripe Terminal at your community event.

---
{ORGANIZATION_NAME} POS System
    """
    
    return send_email(NOTIFICATION_EMAIL, subject, body)

@app.route('/')
def index():
    return render_template('index.html', 
                         organization_name=ORGANIZATION_NAME,
                         organization_logo=ORGANIZATION_LOGO,
                         organization_website=ORGANIZATION_WEBSITE)

@app.route('/admin-readers')
def admin_readers():
    return render_template('admin_readers.html', 
                         organization_name=ORGANIZATION_NAME,
                         organization_logo=ORGANIZATION_LOGO,
                         organization_website=ORGANIZATION_WEBSITE,
                         stripe_publishable_key=os.getenv('STRIPE_PUBLISHABLE_KEY'))

@app.route('/create-connection-token', methods=['POST'])
def create_connection_token():
    try:
        connection_token = stripe.terminal.ConnectionToken.create(
            location=STRIPE_LOCATION_ID
        )
        return jsonify({'secret': connection_token.secret})
    except Exception as e:
        logger.error(f"Error creating connection token: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/debug-env')
def debug_env():
    """Debug endpoint to check environment variables"""
    env_status = {
        'STRIPE_SECRET_KEY': 'SET' if os.getenv('STRIPE_SECRET_KEY') else 'MISSING',
        'STRIPE_PUBLISHABLE_KEY': 'SET' if os.getenv('STRIPE_PUBLISHABLE_KEY') else 'MISSING',
        'STRIPE_LOCATION_ID': os.getenv('STRIPE_LOCATION_ID', 'MISSING'),
        'FROM_EMAIL': os.getenv('FROM_EMAIL', 'MISSING'),
        'ORGANIZATION_NAME': os.getenv('ORGANIZATION_NAME', 'MISSING'),
        'PORT': os.getenv('PORT', 'MISSING'),
        'FLASK_ENV': os.getenv('FLASK_ENV', 'MISSING'),
        'deployment_time': datetime.now().isoformat()
    }
    return jsonify(env_status)

@app.route('/calculate-fees', methods=['POST'])
def calculate_fees():
    try:
        data = request.json
        amount = data.get('amount')
        payment_type = data.get('payment_type')
        membership_type = data.get('membership_type')
        
        # Determine base amount
        if payment_type == 'membership':
            if membership_type == 'individual':
                base_amount = INDIVIDUAL_MEMBERSHIP_AMOUNT
            elif membership_type == 'household':
                base_amount = HOUSEHOLD_MEMBERSHIP_AMOUNT
            else:
                return jsonify({'error': 'Invalid membership type'}), 400
        elif payment_type == 'donation':
            if not amount or amount <= 0:
                return jsonify({'error': 'Invalid donation amount'}), 400
            base_amount = int(amount * 100)  # Convert to cents
        else:
            return jsonify({'error': 'Invalid payment type'}), 400
        
        fee_amount = calculate_fee_amount(base_amount)
        total_with_fees = calculate_total_with_fees(base_amount)
        
        return jsonify({
            'base_amount_cents': base_amount,
            'base_amount_dollars': base_amount / 100,
            'fee_amount_cents': fee_amount,
            'fee_amount_dollars': fee_amount / 100,
            'total_with_fees_cents': total_with_fees,
            'total_with_fees_dollars': total_with_fees / 100
        })
        
    except Exception as e:
        logger.error(f"Error calculating fees: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/create-payment-intent', methods=['POST'])
def create_payment_intent():
    try:
        data = request.json
        payment_type = data.get('payment_type')
        membership_type = data.get('membership_type')
        amount = data.get('amount')
        payer_name = data.get('payer_name', '')
        payer_email = data.get('payer_email', '')
        cover_fees = data.get('cover_fees', False)
        
        # Determine base amount
        if payment_type == 'membership':
            if membership_type == 'individual':
                base_amount = INDIVIDUAL_MEMBERSHIP_AMOUNT
                description = f"Individual membership payment from {payer_name}"
            elif membership_type == 'household':
                base_amount = HOUSEHOLD_MEMBERSHIP_AMOUNT
                description = f"Household membership payment from {payer_name}"
            else:
                return jsonify({'error': 'Invalid membership type'}), 400
        else:
            base_amount = amount
            description = f"Donation from {payer_name}"
        
        # Calculate final amount with fees if requested
        if cover_fees:
            final_amount = calculate_total_with_fees(base_amount)
            fee_amount = calculate_fee_amount(base_amount)
            description += f" (includes ${fee_amount/100:.2f} processing fee)"
        else:
            final_amount = base_amount
        
        metadata = {
            'payment_type': payment_type,
            'payer_name': payer_name,
            'base_amount': str(base_amount),
            'cover_fees': str(cover_fees)
        }
        
        if cover_fees:
            metadata['fee_amount'] = str(calculate_fee_amount(base_amount))
        
        if payer_email:
            metadata['payer_email'] = payer_email
        
        payment_intent = stripe.PaymentIntent.create(
            amount=final_amount,
            currency='usd',
            payment_method_types=['card_present'],
            capture_method='automatic',
            description=description,
            metadata=metadata
        )
        
        logger.info(f"Created PaymentIntent {payment_intent.id} for {payment_type} amount {final_amount}")
        
        return jsonify({
            'client_secret': payment_intent.client_secret,
            'id': payment_intent.id
        })
        
    except Exception as e:
        logger.error(f"Error creating payment intent: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/register-reader', methods=['POST'])
def register_reader():
    try:
        data = request.json
        registration_code = data.get('registration_code')
        
        if not registration_code:
            return jsonify({'error': 'Registration code is required'}), 400
        
        reader = stripe.terminal.Reader.create(
            registration_code=registration_code,
            location=STRIPE_LOCATION_ID
        )
        
        logger.info(f"Successfully registered reader {reader.id} with code {registration_code}")
        
        return jsonify({
            'reader': {
                'id': reader.id,
                'label': reader.label or 'Stripe Reader',
                'status': reader.status
            }
        })
        
    except Exception as e:
        logger.error(f"Error registering reader: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/discover-readers', methods=['POST'])
def discover_readers():
    try:
        logger.info(f"Searching for readers in location: {STRIPE_LOCATION_ID}")
        logger.info(f"Using API key: {stripe.api_key[:12]}...")  # First 12 chars only
        
        # First, let's try to list all readers (no location filter) to debug
        all_readers = stripe.terminal.Reader.list()
        logger.info(f"Total readers in account: {len(all_readers.data)}")
        
        for reader in all_readers.data:
            logger.info(f"Reader {reader.id}: location={reader.location}, status={reader.status}, type={reader.device_type}")
        
        # Now list readers in the specific location
        readers = stripe.terminal.Reader.list(
            location=STRIPE_LOCATION_ID
        )
        
        logger.info(f"Found {len(readers.data)} readers in location {STRIPE_LOCATION_ID}")
        
        reader_list = []
        for reader in readers.data:
            reader_info = {
                'id': reader.id,
                'label': reader.label or 'Stripe Reader',
                'status': reader.status,
                'device_type': reader.device_type,
                'serial_number': reader.serial_number[-4:] if reader.serial_number else 'N/A',  # Last 4 digits only
                'location': reader.location
            }
            reader_list.append(reader_info)
            logger.info(f"Reader found: {reader.label} ({reader.device_type}) - Status: {reader.status}")
        
        return jsonify({
            'readers': reader_list,
            'location_id': STRIPE_LOCATION_ID,
            'total_readers_in_account': len(all_readers.data),
            'debug_all_readers': [{'id': r.id, 'location': r.location, 'status': r.status} for r in all_readers.data]
        })
        
    except Exception as e:
        logger.error(f"Error discovering readers: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/process-payment', methods=['POST'])
def process_payment():
    try:
        data = request.json
        payment_intent_id = data.get('payment_intent_id')
        
        if not payment_intent_id:
            return jsonify({'error': 'Missing payment_intent_id'}), 400
        
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        # Get list of readers and use the first available one
        readers = stripe.terminal.Reader.list(location=STRIPE_LOCATION_ID)
        if not readers.data:
            return jsonify({'error': 'No card readers available. Please set up a reader using the admin interface.'}), 400
        
        # Use the first available reader
        reader_id = readers.data[0].id
        
        reader = stripe.terminal.Reader.process_payment_intent(
            reader_id,
            payment_intent=payment_intent_id
        )
        
        logger.info(f"Processing payment {payment_intent_id} on reader {reader_id}")
        
        return jsonify({
            'status': 'processing',
            'payment_intent_id': payment_intent_id
        })
        
    except Exception as e:
        logger.error(f"Error processing payment: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/payment-status/<payment_intent_id>')
def payment_status(payment_intent_id):
    try:
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        # If payment succeeded and we haven't sent emails yet, send them now
        if payment_intent.status == 'succeeded' and not payment_intent.metadata.get('emails_sent'):
            payer_name = payment_intent.metadata.get('payer_name', 'Unknown')
            payer_email = payment_intent.metadata.get('payer_email')
            payment_type = payment_intent.metadata.get('payment_type', 'payment')
            
            # Log successful transaction
            log_transaction(
                payment_intent_id, payer_name, payer_email, 
                payment_intent.amount, payment_type, 'succeeded', 
                payment_intent.metadata
            )
            
            # Send emails
            receipt_sent = False
            notification_sent = False
            
            if payer_email:
                receipt_sent = send_receipt_email(
                    payer_email, payer_name, payment_intent.amount, 
                    payment_type, payment_intent.id
                )
            
            notification_sent = send_notification_email(
                payer_name, payer_email, payment_intent.amount,
                payment_type, payment_intent.id
            )
            
            # Mark emails as sent to avoid duplicate sends
            try:
                stripe.PaymentIntent.modify(
                    payment_intent_id,
                    metadata={
                        **payment_intent.metadata,
                        'emails_sent': 'true',
                        'receipt_sent': str(receipt_sent),
                        'notification_sent': str(notification_sent)
                    }
                )
            except Exception as e:
                logger.error(f"Error updating payment intent metadata: {str(e)}")
        
        # Log failed/canceled transactions
        elif payment_intent.status in ['canceled', 'payment_failed']:
            payer_name = payment_intent.metadata.get('payer_name', 'Unknown')
            payer_email = payment_intent.metadata.get('payer_email')
            payment_type = payment_intent.metadata.get('payment_type', 'payment')
            
            log_transaction(
                payment_intent_id, payer_name, payer_email,
                payment_intent.amount, payment_type, payment_intent.status,
                payment_intent.metadata
            )
        
        return jsonify({
            'status': payment_intent.status,
            'amount': payment_intent.amount,
            'metadata': payment_intent.metadata
        })
        
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Environment variable debugging at startup
logger.info("=== ENVIRONMENT VARIABLE STATUS (v2) ===")
logger.info(f"STRIPE_SECRET_KEY: {'SET' if os.getenv('STRIPE_SECRET_KEY') else 'MISSING'}")
logger.info(f"STRIPE_LOCATION_ID: {os.getenv('STRIPE_LOCATION_ID', 'MISSING')}")
logger.info(f"FROM_EMAIL: {os.getenv('FROM_EMAIL', 'MISSING')}")
logger.info(f"ORGANIZATION_NAME: {os.getenv('ORGANIZATION_NAME', 'MISSING')}")
logger.info(f"PORT: {os.getenv('PORT', 'MISSING')}")
logger.info(f"Total ENV vars: {len(os.environ)}")
logger.info("=======================================")

if __name__ == '__main__':
    required_vars = ['STRIPE_SECRET_KEY', 'STRIPE_LOCATION_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        exit(1)
    
    logger.info("Starting POS application")
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)