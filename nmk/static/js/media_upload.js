document.addEventListener('DOMContentLoaded', () => {

    const sharedFile = {{ shared_file|default:"null"|safe }};
    const prefillText = "{{ prefill_text|default:''|escapejs }}";

    // Fill description if prefill_text is provided
    if (prefillText) {
        const descriptionInput = document.getElementById('id_description');
        descriptionInput.value = prefillText;

        // Optionally update preview
        const previewContainer = document.getElementById('descriptionPreview');
        const linkifiedText = prefillText.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>');
        previewContainer.innerHTML = linkifiedText;
    }

    // Fill file input if shared_file is provided
    if (sharedFile && sharedFile.name && sharedFile.content) {
        // Decode base64 string → binary data
        const byteCharacters = atob(sharedFile.content);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);

        // Create a Blob with correct MIME type
        let fileType = "application/octet-stream";
        if (sharedFile.name.match(/\.(jpg|jpeg)$/i)) fileType = "image/jpeg";
        else if (sharedFile.name.match(/\.png$/i)) fileType = "image/png";
        else if (sharedFile.name.match(/\.webp$/i)) fileType = "image/webp";
        else if (sharedFile.name.match(/\.mp4$/i)) fileType = "video/mp4";

        const fileBlob = new Blob([byteArray], { type: fileType });

        // Create a File object
        const file = new File([fileBlob], sharedFile.name, { type: fileType });

        // Simulate a file being selected in the input
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        document.getElementById('id_file').files = dataTransfer.files;

        // Show preview
        const event = { target: document.getElementById('id_file') };
        previewFile(event);
    }
});

    $(document).ready(function() {
        // Tag user field with Select2
        $('#id_tags').select2({
            ajax: {
                url: '{% url "user_profile:tag_user_search" %}',
                dataType: 'json',
                delay: 250,
                data: function(params) {
                    return { q: params.term };
                },
                processResults: function(data) {
                    return { results: data.results };
                },
                cache: true
            },
            minimumInputLength: 1,
            placeholder: 'Search for users to tag...',
            allowClear: true,
        });
    });

    function previewFile(event) {
        const input = event.target;
        const previewContainer = document.getElementById('filePreview');
        previewContainer.innerHTML = '';

        const file = input.files[0];
        if (file) {
            const fileType = file.type;
            const previewElement = document.createElement(fileType.startsWith('image/') ? 'img' : 'video');

            previewElement.src = URL.createObjectURL(file);
            previewElement.style.maxWidth = '100%';
            previewElement.style.maxHeight = '400px';

            if (fileType.startsWith('video/')) {
                previewElement.controls = true;
                document.getElementById('videoOptions').style.display = 'block';
            } else {
                document.getElementById('videoOptions').style.display = 'none';
            }

            previewContainer.appendChild(previewElement);
        }
    }

    function convertLinks(event) {
        const input = event.target;
        const previewContainer = document.getElementById('descriptionPreview');
        previewContainer.innerHTML = '';

        const text = input.value;
        const linkifiedText = text.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>');
        previewContainer.innerHTML = linkifiedText;
    }


$(document).ready(function() {

    const MAX_DURATION = 240; // seconds
    let validDuration = true;

    // --- Duration check on file input ---
    $('#id_file').on('change', function(e) {
        const file = e.target.files[0];
        if (!file) return;

        const fileType = file.type;
        if (fileType.startsWith('video/')) {
            const video = document.createElement('video');
            video.preload = 'metadata';

            video.onloadedmetadata = function() {
                window.URL.revokeObjectURL(video.src);
                const duration = video.duration;
                console.log("Video duration:", duration);

                if (duration > MAX_DURATION) {
                    alert(`This video is too long! Maximum allowed duration is ${MAX_DURATION} seconds.`);
                    $('#id_file').val(''); // Clear the input
                    validDuration = false;
                } else {
                    validDuration = true;
                }
            };

            video.onerror = function() {
                alert("Could not read video duration. Please upload a valid video file.");
                $('#id_file').val('');
                validDuration = false;
            };

            video.src = URL.createObjectURL(file);
        } else {
            validDuration = true; // allow images
        }
    });

    // --- Form submission handler ---
    $('#uploadForm').on('submit', function(e) {
        e.preventDefault(); // Stop normal form submission

        if (!validDuration) {
            alert("Please select a valid video (≤ 240 seconds) before uploading.");
            return;
        }

        $('#uploadSpinner').show();        // Show spinner
        $('#submitButton').prop('disabled', true); // Disable button
        $('#uploadProgress').show();       // Show progress bar
        $('#uploadStatus').text('');       // Clear any previous status

        const form = this;
        const formData = new FormData(this);

        $.ajax({
            xhr: function() {
                const xhr = new window.XMLHttpRequest();
                xhr.upload.addEventListener("progress", function(evt) {
                    if (evt.lengthComputable) {
                        const percentComplete = Math.round((evt.loaded / evt.total) * 100);
                        $('#uploadProgress .progress-bar').css('width', percentComplete + '%').text(percentComplete + '%');
                    }
                }, false);
                return xhr;
            },
            url: '{% url "user_profile:upload_media" %}', // Your media upload view
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': '{{ csrf_token }}'

            },
            success: function(response) {
                console.log('Upload successful:', response);
                alert("Upload successful!");
                //window.location.href = "{% url 'user_profile:profile' request.user.id %}";
                // Load profile page via AJAX and inject into #mainContent (or body)

                $.get("{% url 'user_profile:profile' request.user.id %}", function(profileHtml) {
                    $('body').html(profileHtml);
                });

            },
            error: function(xhr, status, error) {
                $('#uploadSpinner').hide();           // Hide spinner
                $('#uploadProgress').hide();          // Hide progress bar
                $('#submitButton').prop('disabled', false); // Re-enable button
                $('#uploadStatus').text("Upload failed. Please try again.");
                console.error("Upload error:", error);
            }
        });
    });
});
