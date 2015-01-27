// Karma configuration
// Generated on Tue Jan 27 2015 16:07:18 GMT+0200 (EET)

module.exports = function(config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine'],
    files: [
      'static/vendor/event-source-polyfill/eventsource.js',
      'static/vendor/moment/min/moment.min.js',
      'static/vendor/angular/angular.js',
      'static/vendor/angular-mocks/angular-mocks.js',
      'static/vendor/angular-cookies/angular-cookies.js',
      'static/vendor/pouchdb/dist/pouchdb.js',
      'static/vendor/angular-bootstrap/ui-bootstrap-tpls.js',
      'static/vendor/angular-timer/dist/angular-timer.js',
      'static/vendor/angular-translate/angular-translate.js',
      'static/vendor/angular-translate-storage-cookie/angular-translate-storage-cookie.js',
      'static/vendor/angular-translate-storage-local/angular-translate-storage-local.js',
      'static/vendor/angular-growl-2/build/angular-growl.js',
      'static/vendor/moment/locale/uk.js',
      'static/vendor/moment/locale/ru.js',
      'static/static/js/*.js',
      {pattern: 'tests/js/*.js', included: true}
    ],


    // list of files to exclude
    exclude: [
    ],


    // preprocess matching files before serving them to the browser
    // available preprocessors: https://npmjs.org/browse/keyword/karma-preprocessor
    preprocessors: {
    },


    // test results reporter to use
    // possible values: 'dots', 'progress'
    // available reporters: https://npmjs.org/browse/keyword/karma-reporter
    reporters: ['progress'],


    // web server port
    port: 9876,


    // enable / disable colors in the output (reporters and logs)
    colors: true,


    // level of logging
    // possible values: config.LOG_DISABLE || config.LOG_ERROR || config.LOG_WARN || config.LOG_INFO || config.LOG_DEBUG
    logLevel: config.LOG_INFO,


    // enable / disable watching file and executing tests whenever any file changes
    autoWatch: true,


    // start these browsers
    // available browser launchers: https://npmjs.org/browse/keyword/karma-launcher
    browsers: ['Chrome'],
    plugins:[
      'karma-jasmine',
      'karma-coverage',
      'karma-chrome-launcher'
    ],

    // Continuous Integration mode
    // if true, Karma captures browsers, runs the tests and exits
    singleRun: false
  });
};
