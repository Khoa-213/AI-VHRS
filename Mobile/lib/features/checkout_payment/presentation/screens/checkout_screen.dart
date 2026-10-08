import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/widgets.dart';

/// Checkout screen with order summary, payment method selection,
/// and WebView-based payment gateway (VNPay / MoMo).
class CheckoutScreen extends ConsumerStatefulWidget {
  final String projectId;

  const CheckoutScreen({super.key, required this.projectId});

  @override
  ConsumerState<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends ConsumerState<CheckoutScreen> {
  String _selectedPaymentMethod = 'vnpay';
  bool _isProcessing = false;
  bool _showPaymentWebView = false;
  WebViewController? _webViewController;

  // Simulated order data
  final String _projectName = 'Wedding Invitation';
  final String _paperSize = 'A4';
  final String _penType = 'Gel Pen';
  final int _pageCount = 1;
  final double _pricePerPage = 25000;

  double get _subtotal => _pageCount * _pricePerPage;
  double get _serviceFee => _subtotal * 0.05;
  double get _total => _subtotal + _serviceFee;

  @override
  void initState() {
    super.initState();
    if (!kIsWeb) {
      _webViewController = WebViewController()
        ..setJavaScriptMode(JavaScriptMode.unrestricted)
        ..setNavigationDelegate(
          NavigationDelegate(
            onUrlChange: (change) {
              // Handle payment callback URL
              final url = change.url ?? '';
              if (url.contains('payment/success') || url.contains('payment/callback')) {
                setState(() => _showPaymentWebView = false);
                _handlePaymentSuccess();
              } else if (url.contains('payment/cancel') || url.contains('payment/failed')) {
                setState(() => _showPaymentWebView = false);
                _handlePaymentFailure();
              }
            },
            onPageStarted: (_) => setState(() => _isProcessing = true),
            onPageFinished: (_) => setState(() => _isProcessing = false),
          ),
        );
    }
  }

  void _handlePaymentSuccess() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Payment received. The robot will start soon.'),
        backgroundColor: AppColors.success,
      ),
    );
    context.go('/tracking');
  }

  void _handlePaymentFailure() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Payment was cancelled or failed.'),
        backgroundColor: AppColors.error,
      ),
    );
  }

  Future<void> _initiatePayment() async {
    setState(() => _isProcessing = true);

    if (kIsWeb) {
      await Future.delayed(const Duration(milliseconds: 600));
      setState(() => _isProcessing = false);
      if (mounted) {
        showDialog(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Web Preview Mode'),
            content: Text(
              'On mobile devices, this opens the ${_selectedPaymentMethod.toUpperCase()} payment gateway in a native WebView.\n\nSimulate payment success now?',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: () {
                  Navigator.pop(ctx);
                  _handlePaymentSuccess();
                },
                child: const Text('Confirm Success'),
              ),
            ],
          ),
        );
      }
      return;
    }

    // Simulate getting payment URL from backend
    await Future.delayed(const Duration(seconds: 1));

    // In production, this URL comes from your backend after creating a payment intent
    final paymentUrl = _selectedPaymentMethod == 'vnpay'
        ? 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html'
        : 'https://test-payment.momo.vn/v2/gateway/pay';

    _webViewController?.loadRequest(Uri.parse(paymentUrl));
    setState(() {
      _showPaymentWebView = true;
      _isProcessing = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_showPaymentWebView && _webViewController != null) {
      return BaseScreen(
        title: 'Payment',
        onBackPressed: () {
          setState(() => _showPaymentWebView = false);
        },
        body: Stack(
          children: [
            WebViewWidget(controller: _webViewController!),
            if (_isProcessing)
              const LoadingView(message: 'Loading payment gateway...', isOverlay: true),
          ],
        ),
      );
    }

    return BaseScreen(
      title: 'Checkout',
      padding: const EdgeInsets.all(20),
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Order Summary Card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(24),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Order summary',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 16),
                  _SummaryRow(label: 'Project', value: _projectName),
                  const SizedBox(height: 8),
                  _SummaryRow(label: 'Paper', value: _paperSize),
                  const SizedBox(height: 8),
                  _SummaryRow(label: 'Pen', value: _penType),
                  const SizedBox(height: 8),
                  _SummaryRow(label: 'Pages', value: '$_pageCount'),
                  const Divider(height: 24),
                  _SummaryRow(
                    label: 'Subtotal',
                    value: Formatters.formatVND(_subtotal),
                  ),
                  const SizedBox(height: 8),
                  _SummaryRow(
                    label: 'Service fee (5%)',
                    value: Formatters.formatVND(_serviceFee),
                  ),
                  const Divider(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Total',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Text(
                        Formatters.formatVND(_total),
                        style: theme.textTheme.headlineMedium?.copyWith(
                          fontFeatures: const [FontFeature.tabularFigures()],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Payment Method Selection
            Text(
              'Payment method',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            _PaymentMethodCard(
              id: 'vnpay',
              name: 'VNPay',
              description: 'Pay with VNPay e-wallet or bank transfer',
              icon: Icons.account_balance_rounded,
              color: const Color(0xFF005BAA),
              isSelected: _selectedPaymentMethod == 'vnpay',
              onTap: () => setState(() => _selectedPaymentMethod = 'vnpay'),
            ),
            const SizedBox(height: 10),
            _PaymentMethodCard(
              id: 'momo',
              name: 'MoMo',
              description: 'Pay with MoMo e-wallet',
              icon: Icons.phone_iphone_rounded,
              color: const Color(0xFFAE2070),
              isSelected: _selectedPaymentMethod == 'momo',
              onTap: () => setState(() => _selectedPaymentMethod = 'momo'),
            ),
            const SizedBox(height: 32),

            // Pay Button
            CustomButton(
              label: 'Pay ${Formatters.formatVND(_total)}',
              onPressed: _initiatePayment,
              isLoading: _isProcessing,
              icon: Icons.lock_outline_rounded,
            ),
            const SizedBox(height: 12),
            Text(
              'Your payment is secured and encrypted.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: AppColors.textTertiary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  final String label;
  final String value;

  const _SummaryRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 14,
            color: AppColors.textSecondary,
          ),
        ),
        Text(
          value,
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: AppColors.textPrimary,
          ),
        ),
      ],
    );
  }
}

class _PaymentMethodCard extends StatelessWidget {
  final String id;
  final String name;
  final String description;
  final IconData icon;
  final Color color;
  final bool isSelected;
  final VoidCallback onTap;

  const _PaymentMethodCard({
    required this.id,
    required this.name,
    required this.description,
    required this.icon,
    required this.color,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: onTap,
      pressedScale: 0.98,
      semanticLabel: name,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? AppColors.ink : AppColors.border,
            width: 1.4,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(icon, color: color, size: 24),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  Text(
                    description,
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.textTertiary,
                    ),
                  ),
                ],
              ),
            ),
            AnimatedOpacity(
              opacity: isSelected ? 1 : 0,
              duration: const Duration(milliseconds: 200),
              child: const Icon(Icons.check_circle_rounded, color: AppColors.ink, size: 22),
            ),
          ],
        ),
      ),
    );
  }
}
