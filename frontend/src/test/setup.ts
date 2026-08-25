/**
 * Test environment setup.
 *
 * WP-UX-UA-01: initialize the bundled i18n instance for every vitest run so
 * components using react-i18next translate deterministically without adding
 * I18nextProvider boilerplate to each test. Tests can still override the
 * active locale via the shared i18n instance (changeLanguage).
 */
import '@testing-library/jest-dom'
import '@/i18n'
