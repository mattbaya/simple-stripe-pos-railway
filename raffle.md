# 🎟️ Raffle Tickets Feature Implementation

## Overview
A comprehensive raffle ticket sales system has been added to the Community POS System, allowing organizations to easily sell raffle tickets alongside donations and memberships. The feature includes pre-set ticket packages, custom quantities, and proper non-tax-deductible receipt handling.

## Key Features

### 🎯 Toggle Control
- **Environment Variable**: `RAFFLE_ENABLED=true/false`
- **Easy Activation**: Set to `true` to enable raffle button, `false` to hide it
- **Dynamic Layout**: Automatically switches between 3-column (without raffle) and 4-column (with raffle) button layout
- **No Code Changes**: Toggle functionality without touching application code

### 🎨 User Interface
- **4th Button**: Professional raffle tickets button with gradient styling
- **Organization Image**: Uses custom raffle image from https://southwilliamstown.org/SWCA-raffle.png
- **Fallback Design**: Displays 🎟️ emoji if custom image fails to load (perfect for GitHub deployments)
- **Responsive Design**: Maintains clean layout across all screen sizes

### 💰 Pricing Structure
- **Fixed Price**: $0.80 per ticket (80 cents)
- **Pre-set Packages**:
  - 🎟️ 5 tickets for $5.00 ($1.00 per ticket - discounted)
  - 🎟️ 12 tickets for $10.00 ($0.83 per ticket - discounted) 
  - 🎟️ 25 tickets for $20.00 ($0.80 per ticket - standard rate)
- **Custom Quantities**: Users can enter quantities of 26+ tickets (preset buttons cover 5-25)
- **Real-time Calculation**: Live display of total cost and ticket count

### 💳 Payment Processing
- **Fee Coverage**: Users can opt to cover 2.9% + $0.30 Stripe processing fees
- **Stripe Integration**: Full integration with existing payment processing system
- **Metadata Tracking**: Ticket quantity and purchase details stored in payment metadata
- **Transaction Logging**: Raffle purchases logged with quantity and pricing information

## Technical Implementation

### Backend Changes (app/main.py)

#### Environment Configuration
```python
# Raffle configuration
RAFFLE_ENABLED = os.getenv('RAFFLE_ENABLED', 'false').lower() == 'true'
RAFFLE_PRICE_PER_TICKET = 80  # 80 cents per ticket
```

#### Fee Calculation Updates (Line 441-472)
- Added `raffle_quantity` parameter to `/calculate-fees` endpoint
- Handles raffle ticket amount calculation: `quantity * 80 cents`
- Returns proper fee calculations for raffle purchases

#### Payment Intent Creation (Line 491-549) 
- Added `raffle_quantity` parameter handling
- Creates payment descriptions: "Raffle tickets purchase from {name} - {quantity} tickets"
- Stores raffle metadata for receipt generation and reporting

#### Email System Enhancements
- **New Function**: `send_raffle_receipt_email()` for non-tax-deductible confirmations
- **Template Selection**: Automatically chooses appropriate email template based on payment type
- **Metadata Handling**: Passes raffle quantity to receipt generation

### Frontend Changes (templates/index.html)

#### Button Layout (Line 212-252)
- **Conditional Display**: Uses Jinja2 templating to show/hide raffle button
- **4-Column Layout**: When raffle enabled, all buttons use `col-md-3` classes
- **3-Column Fallback**: When raffle disabled, uses `col-md-4` classes
- **Custom Styling**: Orange gradient background with hover effects

#### Raffle Selection Interface (Line 275-301)
```html
<div id="raffle-quantity" class="mb-3" style="display: none;">
    <label for="raffle-tickets" class="form-label">Number of Raffle Tickets</label>
    <div class="row g-2 mb-3">
        <div class="col-4">
            <button type="button" class="btn btn-outline-primary w-100" onclick="selectRafflePackage(5)">
                🎟️ 5 for $5
            </button>
        </div>
        <!-- Additional package buttons -->
    </div>
    <div class="mb-2">
        <label for="custom-raffle-quantity" class="form-label">Or enter custom quantity:</label>
        <input type="number" class="form-control" id="custom-raffle-quantity" min="1" step="1" placeholder="Enter quantity" onchange="updateRaffleCalculation()">
    </div>
    <div class="alert alert-info">
        <small><strong>Total:</strong> $<span id="raffle-total">0.00</span> for <span id="raffle-ticket-count">0</span> tickets</small>
    </div>
</div>
```

#### JavaScript Functions
- **`selectRafflePackage(quantity)`**: Sets pre-defined quantities from package buttons
- **`updateRaffleCalculation()`**: Real-time price calculation display
- **`selectPaymentType('raffle')`**: Handles raffle-specific form state management
- **Form Reset**: Clears raffle fields when switching payment types

### Email Templates

#### New Raffle Email Template (templates/raffle_purchase_email.html)
- **Non-Tax-Deductible Focus**: Clear messaging about tax implications
- **Professional Layout**: Matches existing email design with raffle-specific styling
- **Good Luck Messaging**: 🍀 Good Luck in the Raffle Drawing! 🍀
- **Purchase Details**: Ticket quantity, total amount, price per ticket
- **Tax Warning**: Prominent red-bordered section explaining non-deductible status

#### Template Variables
```html
{payer_name} - Customer name
{amount_formatted} - Total purchase amount ($X.XX)
{payment_date} - Purchase date
{organization_name} - Organization name
{payment_intent_id} - Stripe transaction ID
{raffle_quantity} - Number of tickets purchased
```

#### Email Content Highlights
- **Header**: Organization letterhead with raffle-specific styling
- **Purchase Confirmation**: Clear ticket quantity and pricing breakdown
- **Good Luck Section**: Encouraging message with lottery/raffle emojis
- **Tax Notice**: Explicit non-deductible warning in highlighted box
- **Professional Signature**: Maintains organization branding

## Configuration Instructions

### Environment Variables
Add to your Railway/deployment environment:
```env
RAFFLE_ENABLED=true  # Enable raffle ticket sales
```

### For Organizations Using Local Config
1. Place custom raffle image at: `local-config/templates/raffle-image.png`
2. Create custom raffle email template at: `local-config/templates/raffle_purchase_email.html`
3. System automatically prefers local-config files when available

### Disabling Raffle Feature
Set `RAFFLE_ENABLED=false` or remove the environment variable entirely. The raffle button will be hidden and the layout will revert to the standard 3-button design.

## Business Logic

### Tax Implications
- **Non-Deductible**: Raffle ticket purchases are considered payment for goods/services
- **Clear Communication**: Both user interface and email receipts explain tax status
- **Receipt Differentiation**: Separate email template prevents confusion with donation receipts
- **Admin Notifications**: Organization emails clearly identify raffle vs. donation funds

### Pricing Strategy
- **Volume Discounts**: Smaller packages offer better per-ticket rates to encourage sales
- **Standard Rate**: $0.80 per ticket for quantities above package deals
- **Transparent Pricing**: Real-time calculation shows exact costs

### Payment Flow
1. User selects raffle tickets from main interface
2. Chooses pre-set package or enters custom quantity
3. Reviews total cost and ticket count
4. Optionally covers processing fees
5. Completes payment via Stripe Terminal
6. Receives non-tax-deductible confirmation email
7. Organization receives detailed notification with raffle-specific information

## File Changes Summary

### New Files Created
- `templates/raffle_purchase_email.html` - Non-tax-deductible email template

### Modified Files
- `app/main.py` - Backend raffle logic, payment processing, email handling
- `templates/index.html` - UI for raffle button, form, and JavaScript
- `CLAUDE.md` - Feature documentation and configuration
- `README.md` - Deployment instructions and feature listing

### Key Functions Added
- `send_raffle_receipt_email()` - Raffle-specific email generation
- `selectRafflePackage()` - JavaScript package selection
- `updateRaffleCalculation()` - Real-time pricing display

## Testing Checklist

### Functionality Tests
- [ ] Raffle button appears when `RAFFLE_ENABLED=true`
- [ ] Raffle button hidden when `RAFFLE_ENABLED=false`
- [ ] Package buttons (5, 12, 25) set correct quantities
- [ ] Custom quantity input calculates pricing correctly
- [ ] Fee coverage option works with raffle purchases
- [ ] Payment processing completes successfully
- [ ] Success modal shows correct ticket quantity

### Email Tests
- [ ] Raffle receipt email uses correct template
- [ ] Non-tax-deductible warning displayed prominently
- [ ] Organization notification includes raffle details
- [ ] Email fallback works if template loading fails

### Layout Tests
- [ ] 4-column layout when raffle enabled
- [ ] 3-column layout when raffle disabled
- [ ] Responsive design works on mobile devices
- [ ] Form fields reset properly when switching payment types

## Deployment Notes

### Railway Deployment
1. Add `RAFFLE_ENABLED=true` to Railway environment variables
2. Deploy updated code
3. Test with small raffle purchase
4. Verify email delivery and content

### GitHub Version
- Uses emoji fallback (🎟️) when organization image unavailable
- Maintains full functionality without custom assets
- Perfect for testing and development environments

## Support Information

### Common Issues
- **Image Not Loading**: System automatically falls back to emoji
- **Email Template Errors**: Graceful fallback to simple HTML email
- **Calculation Errors**: JavaScript validates input and shows real-time updates

### Admin Notifications
Organization emails for raffle purchases include:
- Clear "RAFFLE TICKETS" designation
- Ticket quantity purchased
- "RAFFLE FUNDS: not tax-deductible" notation
- Standard transaction details

This comprehensive raffle system enhances fundraising capabilities while maintaining the professional, user-friendly experience of the existing POS system.