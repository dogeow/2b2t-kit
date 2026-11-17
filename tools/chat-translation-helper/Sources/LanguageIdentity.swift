import Foundation
import NaturalLanguage

enum LanguageIdentity {
    static func resolvedSource(for request: TranslationRequest) -> String? {
        if request.from != "auto" { return request.from }
        let letters = request.text.unicodeScalars.filter { CharacterSet.letters.contains($0) }
        guard !letters.isEmpty else { return nil }
        if letters.count <= 3 && letters.allSatisfy({ $0.isASCII }) { return "en" }
        let recognizer = NLLanguageRecognizer()
        recognizer.processString(request.text)
        let hypotheses = recognizer.languageHypotheses(withMaximum: 1)
        let language = hypotheses.first.flatMap { $0.value >= 0.75 ? $0.key : nil }
        if let language, language != .traditionalChinese {
            return language.rawValue
        }
        // Ambiguous chat falls back to Chinese when it contains Han, otherwise English.
        if language == nil && request.text.range(of: #"\p{Han}"#, options: .regularExpression) == nil {
            return "en"
        }
        // Shared Han glyphs do not establish a Traditional writing system.
        let simplified = request.text.applyingTransform(StringTransform("Traditional-Simplified"), reverse: false)
        return simplified == request.text ? "zh-Hans" : "zh-Hant"
    }

    static func chineseScriptTranslation(for request: TranslationRequest) -> TranslationResult? {
        guard let tag = resolvedSource(for: request) else { return nil }
        let source = Locale.Language(identifier: tag)
        let target = Locale.Language(identifier: request.to)
        guard source.languageCode?.identifier == "zh", target.languageCode?.identifier == "zh",
              let fromScript = source.script?.identifier, let toScript = target.script?.identifier,
              fromScript != toScript else { return nil }
        let rule = toScript == "Hans" ? "Traditional-Simplified" : "Simplified-Traditional"
        guard let result = request.text.applyingTransform(StringTransform(rule), reverse: false) else { return nil }
        return TranslationResult(translation: result, sourceLanguage: source.minimalIdentifier,
                                 targetLanguage: target.minimalIdentifier, id: request.id)
    }
    // Whole word only: player names such as Diedrich must still be translated.
    static func preservesDeathMessage(_ text: String) -> Bool {
        text.range(of: #"(?i)(?<![\p{L}\p{N}_])died(?![\p{L}\p{N}_])"#,
                   options: .regularExpression) != nil
    }

    /// Return the original only when source and target are the same language
    /// and writing system. Regions may differ; Chinese Hans/Hant may not.
    static func unchangedTranslation(for request: TranslationRequest) -> TranslationResult? {
        if preservesDeathMessage(request.text) {
            return TranslationResult(translation: request.text, sourceLanguage: request.from,
                                     targetLanguage: request.to, id: request.id)
        }
        let sourceTag: String
        guard let resolved = resolvedSource(for: request) else { return nil }
        sourceTag = resolved
        let source = Locale.Language(identifier: sourceTag)
        let target = Locale.Language(identifier: request.to)
        guard let sourceCode = source.languageCode?.identifier.lowercased(),
              let targetCode = target.languageCode?.identifier.lowercased(),
              sourceCode == targetCode,
              source.script?.identifier.lowercased() == target.script?.identifier.lowercased() else { return nil }
        return TranslationResult(translation: request.text, sourceLanguage: source.minimalIdentifier,
                                 targetLanguage: target.minimalIdentifier, id: request.id)
    }
}
