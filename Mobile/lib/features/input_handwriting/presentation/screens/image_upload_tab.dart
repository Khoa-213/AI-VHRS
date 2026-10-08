import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../../core/widgets/widgets.dart';

/// Image upload tab: pick photo, preview, adjust contrast threshold, and submit.
class ImageUploadTab extends ConsumerStatefulWidget {
  final String projectId;

  const ImageUploadTab({super.key, required this.projectId});

  @override
  ConsumerState<ImageUploadTab> createState() => _ImageUploadTabState();
}

class _ImageUploadTabState extends ConsumerState<ImageUploadTab>
    with AutomaticKeepAliveClientMixin {
  File? _selectedImage;
  double _contrastThreshold = AppConstants.defaultContrastThreshold;
  int _rotation = 0; // 0, 90, 180, 270
  bool _isUploading = false;

  @override
  bool get wantKeepAlive => true;

  Future<void> _pickImage(ImageSource source) async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(
      source: source,
      maxWidth: AppConstants.maxImageWidth.toDouble(),
      maxHeight: AppConstants.maxImageHeight.toDouble(),
      imageQuality: 90,
    );

    if (picked != null) {
      setState(() => _selectedImage = File(picked.path));
    }
  }

  void _rotateImage() {
    setState(() => _rotation = (_rotation + 90) % 360);
  }

  Future<void> _handleSubmit() async {
    if (_selectedImage == null) return;

    setState(() => _isUploading = true);

    // Simulate upload — replace with actual API call
    await Future.delayed(const Duration(seconds: 2));

    setState(() => _isUploading = false);

    if (mounted) {
      context.push('/projects/${widget.projectId}/trajectory');
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Image Preview Area
          GestureDetector(
            onTap: () => _showImageSourceDialog(),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              height: 280,
              decoration: BoxDecoration(
                color: AppColors.surfaceVariant,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: _selectedImage != null ? AppColors.primary : AppColors.border,
                  width: _selectedImage != null ? 2 : 1,
                  strokeAlign: BorderSide.strokeAlignInside,
                ),
              ),
              child: _selectedImage != null
                  ? ClipRRect(
                      borderRadius: BorderRadius.circular(14),
                      child: Transform.rotate(
                        angle: _rotation * 3.14159 / 180,
                        child: Image.file(
                          _selectedImage!,
                          fit: BoxFit.contain,
                          width: double.infinity,
                        ),
                      ),
                    )
                  : Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.cloud_upload_outlined,
                          size: 56,
                          color: AppColors.primary.withOpacity(0.4),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Tap to upload a photo',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: AppColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Supports JPG, PNG up to ${AppConstants.maxImageWidth}px',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: AppColors.textTertiary,
                          ),
                        ),
                      ],
                    ),
            ),
          ),
          const SizedBox(height: 20),

          // Image Tools (visible when image is selected)
          if (_selectedImage != null) ...[
            Row(
              children: [
                Expanded(
                  child: CustomButton(
                    label: 'Rotate',
                    onPressed: _rotateImage,
                    icon: Icons.rotate_right_rounded,
                    style: CustomButtonStyle.outline,
                    isExpanded: true,
                    height: 44,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CustomButton(
                    label: 'Re-pick',
                    onPressed: _showImageSourceDialog,
                    icon: Icons.refresh_rounded,
                    style: CustomButtonStyle.outline,
                    isExpanded: true,
                    height: 44,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),

            // Contrast Threshold Slider
            Text(
              'Contrast Threshold',
              style: theme.textTheme.titleSmall?.copyWith(
                color: AppColors.textSecondary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(Icons.brightness_low, size: 20, color: AppColors.textTertiary),
                Expanded(
                  child: Slider(
                    value: _contrastThreshold,
                    min: AppConstants.minContrastThreshold,
                    max: AppConstants.maxContrastThreshold,
                    divisions: 255,
                    activeColor: AppColors.primary,
                    inactiveColor: AppColors.border,
                    label: _contrastThreshold.round().toString(),
                    onChanged: (value) => setState(() => _contrastThreshold = value),
                  ),
                ),
                const Icon(Icons.brightness_high, size: 20, color: AppColors.textTertiary),
              ],
            ),
            Text(
              'Threshold: ${_contrastThreshold.round()} / 255',
              style: theme.textTheme.bodySmall?.copyWith(color: AppColors.textTertiary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 32),

            // Submit Button
            CustomButton(
              label: 'Process image',
              onPressed: _handleSubmit,
              isLoading: _isUploading,
              icon: Icons.auto_fix_high_rounded,
            ),
          ],
        ],
      ),
    );
  }

  void _showImageSourceDialog() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.border,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(height: 20),
              ListTile(
                leading: Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: AppColors.primary.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.camera_alt_outlined, color: AppColors.primary),
                ),
                title: const Text('Take Photo'),
                subtitle: const Text('Use camera to capture handwriting'),
                onTap: () {
                  Navigator.pop(context);
                  _pickImage(ImageSource.camera);
                },
              ),
              const SizedBox(height: 8),
              ListTile(
                leading: Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: AppColors.secondary.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.photo_library_outlined, color: AppColors.secondary),
                ),
                title: const Text('Choose from Gallery'),
                subtitle: const Text('Select an existing photo'),
                onTap: () {
                  Navigator.pop(context);
                  _pickImage(ImageSource.gallery);
                },
              ),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}
