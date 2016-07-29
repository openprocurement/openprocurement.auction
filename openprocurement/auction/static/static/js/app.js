var app = angular.module('auction', ['ui.bootstrap', 'ngCookies', 'pascalprecht.translate', 'timer', 'angular-growl', 'angular-ellipses', 'GTMLogger']);
var db = {};
var bidder_id = "0";
var auction_doc_id = auction_doc_id || "";
var db_url = db_url || "";

app.constant('AuctionConfig', {
  auction_doc_id: auction_doc_id,
  remote_db: db_url,
  restart_retries: 10,
  default_lang: 'uk',
  debug: false
});

app.filter('formatnumber', ['$filter',
  function(filter) {
    return function(val) {
      return (filter('number')(val) || "").replace(/,/g, " ") || "";
    }
  }
]);

app.config(['$logProvider', 'AuctionConfig', 'growlProvider', 'GTMLoggerProvider', function($logProvider, AuctionConfig, growlProvider, GTMLoggerProvider) {
    GTMLoggerProvider.level('INFO').includeTimestamp( true )
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

function logMSG(MSG)
{
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.open("POST", '/log', true);
    xmlHttp.send(JSON.stringify(MSG));
}

