/* eslint-disable @typescript-eslint/no-var-requires */
const path = require("path");

/** @type {import('webpack').Configuration[]} */
module.exports = [
  // Extension host bundle (Node.js)
  {
    name: "extension",
    target: "node",
    mode: "none",
    entry: "./src/extension.ts",
    output: {
      path: path.resolve(__dirname, "dist"),
      filename: "extension.js",
      libraryTarget: "commonjs2",
    },
    externals: {
      vscode: "commonjs vscode",
      bufferutil: "commonjs bufferutil",
      "utf-8-validate": "commonjs utf-8-validate",
    },
    resolve: {
      extensions: [".ts", ".js"],
    },
    module: {
      rules: [
        {
          test: /\.ts$/,
          exclude: /node_modules/,
          use: "ts-loader",
        },
      ],
    },
    devtool: "nosources-source-map",
  },
  // Webview bundle (Browser)
  {
    name: "webview",
    target: "web",
    mode: "none",
    entry: "./webview-ui/index.tsx",
    output: {
      path: path.resolve(__dirname, "dist"),
      filename: "webview.js",
    },
    resolve: {
      extensions: [".tsx", ".ts", ".js"],
    },
    module: {
      rules: [
        {
          test: /\.tsx?$/,
          exclude: /node_modules/,
          use: {
            loader: "ts-loader",
            options: {
              compilerOptions: {
                module: "esnext",
                moduleResolution: "bundler",
                jsx: "react-jsx",
                target: "ES2020",
                lib: ["ES2020", "DOM"],
              },
            },
          },
        },
        {
          test: /\.css$/,
          use: ["style-loader", "css-loader"],
        },
      ],
    },
    devtool: "nosources-source-map",
  },
];
