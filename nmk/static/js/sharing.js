// SHARING JAVASCRIPT - DROP-IN READY
// Add this to a file like static/js/sharing.js

/**
 * Complete Sharing System with Native Share API Support
 * 
 * Features:
 * - Native mobile sharing (Web Share API)
 * - Platform-specific share links
 * - Copy link functionality
 * - QR code generation
 * - Download functionality
 */

class MediaSharing {
    constructor(mediaId, shareUrl, title, description, mediaUrl, mediaType) {
        this.mediaId = mediaId;
        this.shareUrl = shareUrl;
        this.title = title;
        this.description = description;
        this.mediaUrl = mediaUrl;
        this.mediaType = mediaType;
    }

    /**
     * Open share modal
     */
    openShareModal() {
        // Fetch share data via AJAX
        fetch(`/media/${this.mediaId}/share/`, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.showShareModal(data);
            }
        })
        .catch(error => {
            console.error('Error fetching share data:', error);
            alert('Error loading share options');
        });
    }

    /**
     * Show share modal with options
     */
    showShareModal(data) {
        const modal = this.createShareModal(data);
        document.body.appendChild(modal);
        
        // Show modal with animation
        setTimeout(() => modal.classList.add('active'), 10);
        
        // Setup event listeners
        this.setupModalListeners(modal, data);
    }

    /**
     * Create share modal HTML
     */
    createShareModal(data) {
        const modal = document.createElement('div');
        modal.className = 'share-modal-overlay';
        modal.innerHTML = `
            <div class="share-modal">
                <div class="share-modal-header">
                    <h3>Share this post</h3>
                    <button class="share-close-btn" onclick="this.closest('.share-modal-overlay').remove()">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M18 6L6 18M6 6l12 12" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                    </button>
                </div>
                
                <div class="share-modal-body">
                    ${this.getNativeShareButton()}
                    
                    <div class="share-link-section">
                        <input type="text" class="share-link-input" value="${data.share_url}" readonly>
                        <button class="copy-link-btn" data-url="${data.share_url}">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" stroke-width="2"/>
                                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke-width="2"/>
                            </svg>
                            Copy Link
                        </button>
                    </div>
                    
                    <div class="share-platforms">
                        <a href="${data.share_links.whatsapp}" target="_blank" class="share-platform-btn whatsapp">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                            </svg>
                            WhatsApp
                        </a>
                        
                        <a href="${data.share_links.facebook}" target="_blank" class="share-platform-btn facebook">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                            </svg>
                            Facebook
                        </a>
                        
                        <a href="${data.share_links.twitter}" target="_blank" class="share-platform-btn twitter">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z"/>
                            </svg>
                            Twitter
                        </a>
                        
                        <a href="${data.share_links.telegram}" target="_blank" class="share-platform-btn telegram">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M11.944 0A12 12 0 000 12a12 12 0 0012 12 12 12 0 0012-12A12 12 0 0012 0a12 12 0 00-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 01.171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
                            </svg>
                            Telegram
                        </a>
                        
                        <a href="${data.share_links.email}" class="share-platform-btn email">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" stroke-width="2"/>
                                <polyline points="22,6 12,13 2,6" stroke-width="2"/>
                            </svg>
                            Email
                        </a>
                        
                        <button class="share-platform-btn qr-code" data-media-id="${this.mediaId}">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <rect x="3" y="3" width="7" height="7" stroke-width="2"/>
                                <rect x="14" y="3" width="7" height="7" stroke-width="2"/>
                                <rect x="3" y="14" width="7" height="7" stroke-width="2"/>
                                <rect x="14" y="14" width="3" height="3" fill="currentColor"/>
                                <rect x="18" y="14" width="3" height="3" fill="currentColor"/>
                                <rect x="14" y="18" width="3" height="3" fill="currentColor"/>
                                <rect x="18" y="18" width="3" height="3" fill="currentColor"/>
                            </svg>
                            QR Code
                        </button>
                        
                        <button class="share-platform-btn download" data-media-id="${this.mediaId}">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                            Download
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        return modal;
    }

    /**
     * Get native share button HTML if supported
     */
    getNativeShareButton() {
        if (navigator.share) {
            return `
                <button class="native-share-btn" data-native-share="true">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <circle cx="18" cy="5" r="3" stroke-width="2"/>
                        <circle cx="6" cy="12" r="3" stroke-width="2"/>
                        <circle cx="18" cy="19" r="3" stroke-width="2"/>
                        <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" stroke-width="2"/>
                        <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" stroke-width="2"/>
                    </svg>
                    Share via...
                </button>
            `;
        }
        return '';
    }

    /**
     * Setup event listeners for modal
     */
    setupModalListeners(modal, data) {
        // Copy link button
        const copyBtn = modal.querySelector('.copy-link-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => this.copyToClipboard(data.share_url, copyBtn));
        }

        // Native share button
        const nativeShareBtn = modal.querySelector('[data-native-share]');
        if (nativeShareBtn) {
            nativeShareBtn.addEventListener('click', () => this.nativeShare(data));
        }

        // QR code button
        const qrBtn = modal.querySelector('.qr-code');
        if (qrBtn) {
            qrBtn.addEventListener('click', () => this.showQRCode(data.share_url));
        }

        // Download button
        const downloadBtn = modal.querySelector('.download');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', () => this.downloadMedia());
        }

        // Close on overlay click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
    }

    /**
     * Native share using Web Share API
     */
    async nativeShare(data) {
        if (navigator.share) {
            try {
                await navigator.share({
                    title: data.title,
                    text: data.description,
                    url: data.share_url
                });
                console.log('Shared successfully');
            } catch (error) {
                if (error.name !== 'AbortError') {
                    console.error('Error sharing:', error);
                }
            }
        }
    }

    /**
     * Copy link to clipboard
     */
    async copyToClipboard(text, button) {
        try {
            await navigator.clipboard.writeText(text);
            
            // Visual feedback
            const originalText = button.innerHTML;
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <polyline points="20 6 9 17 4 12" stroke-width="2" stroke-linecap="round"/>
                </svg>
                Copied!
            `;
            button.classList.add('copied');
            
            setTimeout(() => {
                button.innerHTML = originalText;
                button.classList.remove('copied');
            }, 2000);
        } catch (error) {
            console.error('Error copying to clipboard:', error);
            
            // Fallback for older browsers
            const input = document.querySelector('.share-link-input');
            input.select();
            document.execCommand('copy');
            
            button.textContent = 'Copied!';
            setTimeout(() => {
                button.textContent = 'Copy Link';
            }, 2000);
        }
    }

    /**
     * Show QR code in modal
     */
    showQRCode(shareUrl) {
        const qrModal = document.createElement('div');
        qrModal.className = 'qr-modal-overlay';
        qrModal.innerHTML = `
            <div class="qr-modal">
                <div class="qr-modal-header">
                    <h3>Scan QR Code</h3>
                    <button class="share-close-btn" onclick="this.closest('.qr-modal-overlay').remove()">×</button>
                </div>
                <div class="qr-modal-body">
                    <img src="/media/${this.mediaId}/qr/" alt="QR Code" class="qr-code-image">
                    <p>Scan this code to open the post</p>
                </div>
            </div>
        `;
        
        document.body.appendChild(qrModal);
        setTimeout(() => qrModal.classList.add('active'), 10);
        
        qrModal.addEventListener('click', (e) => {
            if (e.target === qrModal) {
                qrModal.remove();
            }
        });
    }

    /**
     * Download media file
     */
    downloadMedia() {
        window.location.href = `/media/${this.mediaId}/download/`;
    }
}

// Global function to trigger sharing
function shareMedia(mediaId, shareUrl, title, description, mediaUrl, mediaType) {
    const sharing = new MediaSharing(mediaId, shareUrl, title, description, mediaUrl, mediaType);
    sharing.openShareModal();
}

// Export for use in other scripts
window.MediaSharing = MediaSharing;
window.shareMedia = shareMedia;
