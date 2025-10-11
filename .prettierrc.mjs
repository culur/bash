import defineConfig from '@culur/config-prettier/factory';

export default defineConfig({
  plugins: ['prettier-plugin-sh'],
  // overrides: [
  //   {
  //     files: ['**/*.sh', '**/*.bash', '**/*.zsh'],
  //     options: { parser: 'sh' },
  //   },
  // ],
});
