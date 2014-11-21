angular.module('auction')
  .factory('AuctionUtils', ['$filter', '$timeout', function($filter, $timeout) {
    // Format msg for timer
    function timer_message(auction, bidder) {
      if (auction.current_stage < 0) {
        // * until the auction starts
        return "until the auction starts"
      };
      // * until your turn
      // * until your turn ends
      // * until the round ends
      // * until the results announcement
      // * after the auction was completed
      return ""
    };
    // Get bidder_id from query
    function get_bidder_id() {
        var query = window.location.search.substring(1);
        var vars = query.split('&');
        for (var i = 0; i < vars.length; i++) {
          var pair = vars[i].split('=');
          if (decodeURIComponent(pair[0]) == 'bidder_id') {
            return decodeURIComponent(pair[1]);
          }
        }
      }
      // Format date with traslations
    function format_date(date, format) {
      return $filter('date')(date, $filter('translate')(format));
    };

    // Get round data
    function get_round_data(pause_index, auction_doc, Rounds) {
      if (pause_index <= Rounds[0]) {
        return {
          'type': 'pause',
          'data': ['', '1', ]
        }
      }
      for (var i in Rounds) {
        if (pause_index < Rounds[i]) {
          return {
            'type': 'round',
            'data': parseInt(i) - 1
          }
        } else if ((pause_index == Rounds[i]) && (pause_index != auction_doc.stages.length - 1)) {
          return {
            'type': 'pause',
            'data': [(parseInt(i) - 1).toString(), (parseInt(i)).toString(), ]
          }
        }
      };
      return {
        'type': 'finish'
      }
    }
    // Scroll functionality
    function scroll_to_stage (stage) {
      $timeout(function() {
        var stage_el = document.getElementById('stage-' + stage.toString())
        if (stage_el) {
          window.scrollBy(0, stage_el.getBoundingClientRect().top);
          window.scrollBy(0, -100);
        }
      }, 500);
    }
    return {
      'timer_message': timer_message,
      'get_bidder_id': get_bidder_id,
      'format_date': format_date,
      'get_round_data': get_round_data,
      'scroll_to_stage': scroll_to_stage
    }
  }]);