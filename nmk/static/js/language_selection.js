function googleTranslateElementInit() {
    new google.translate.TranslateElement(
        {
            pageLanguage: 'en',
            // includedLanguages: 'en,hi,mr,ta,bn,te,ml,gu,kn,pa,or,ur',
            layout: google.translate.TranslateElement.InlineLayout.HORIZONTAL
        },
        'google_translate_element'
    );
}
