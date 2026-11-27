// The standalone bundle compiles the canonical enum so newly registered keys
// cannot drift from the runtime registry consumed by the ten locale modules.
export { default } from './i18nKey.ts';
