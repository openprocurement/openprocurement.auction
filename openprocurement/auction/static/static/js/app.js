var app = angular.module('auction', ['ui.bootstrap', 'ngCookies', 'pascalprecht.translate', 'timer', 'angular-growl']);
var db = {};
var bidder_id = "0";
var auction_doc_id = auction_doc_id||"";
var db_url = db_url||"";

app.constant('AuctionConfig', {
    auction_doc_id: auction_doc_id,
    remote_db: db_url,
    restart_retries: 10,
    default_lang: 'uk',
    debug: true
});

app.filter('formatnumber', ['$filter',
    function(filter) {
        return function(val) {
            return (filter('number')(val) || "").replace(/,/g, " ") || "";
        }
    }
]);

app.config(['$logProvider', 'AuctionConfig', 'growlProvider', function($logProvider, AuctionConfig, growlProvider) {
    $logProvider.debugEnabled(AuctionConfig.debug); // default is true
    growlProvider.globalTimeToLive({
        success: 4000,
        error: 10000,
        warning: 10000,
        info: 4000
    });
    growlProvider.globalPosition('top-center');
    growlProvider.onlyUniqueMessages(false);
}]);


// Catch error log msgs
app.config([ "$provide", function( $provide ) {
    // Use the `decorator` solution to substitute or attach behaviors to
    // original service instance; @see angular-mocks for more examples....

    $provide.decorator( '$log', [ "$delegate", function( $delegate )
    {
        // Save the original $log.debug()
        var origDebug = $delegate.error;

        $delegate.error = function () {
            var args = [].slice.call(arguments);
            dataLayer.push({"event": "JS.error", "MESSAGE": args.join(" ")});
            origDebug.apply(null, arguments)
        };

        return $delegate;
    }]);
}]);


// Catch exceptions
app.factory('$exceptionHandler', function() {
  return function(exception, cause) {
    dataLayer.push({"event": "JS.error", "MESSAGE": exception.message});
    throw exception;
  };
});
