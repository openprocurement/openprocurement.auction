angular.module('auction')
  .factory('AuctionUtils', ['$filter', '$timeout', '$log', function ($filter, $timeout, $log) {
    // Format msg for timer
    'use strict';

    function prepare_info_timer_data(current_time, auction, bidder_id, Rounds) {
      var i;
      if (auction.current_stage < 0) {
        return {
          'countdown': ((new Date(auction.stages[0].start) - current_time) / 1000),
          'start_time': false,
          'msg': 'until the auction starts'
        };
      }
      if (auction.current_stage === (auction.stages.length - 1)) {
        var client_time = new Date();
        var ends_time = new Date(auction.stages[auction.current_stage].start);
        if (client_time < ends_time) {
          ends_time = client_time;
        }
        return {
          'countdown': false,
          'start_time': ends_time,
          'msg': 'Аuction was completed'
        };
      }
      if (bidder_id) {
        if (auction.stages[auction.current_stage].bidder_id === bidder_id) {
          return {
            'countdown': ((new Date(auction.stages[auction.current_stage + 1].start) - current_time) / 1000),
            'start_time': false,
            'msg': 'until your turn ends'
          };
        }
        var all_rounds = Rounds.concat(auction.stages.length - 1);
        for (i in all_rounds) {
          if (auction.current_stage < all_rounds[i]) {
            for (var index = auction.current_stage; index <= all_rounds[i]; index++) {
              if ((auction.stages[index].bidder_id) && (auction.stages[index].bidder_id === bidder_id)) {
                return {
                  'countdown': ((new Date(auction.stages[index].start) - current_time) / 1000),
                  'start_time': false,
                  'msg': 'until your turn'
                };
              }
            }
            break;
          }
        }
      }
      for (i in Rounds) {
        if (auction.current_stage == Rounds[i]) {
          return {
            'countdown': ((new Date(auction.stages[auction.current_stage + 1].start) - current_time) / 1000),
            'start_time': false,
            'msg': 'until the round starts'
          };
        }
        if (auction.current_stage < Rounds[i]) {
          return {
            'countdown': ((new Date(auction.stages[Rounds[i]].start) - current_time) / 1000),
            'start_time': false,
            'msg': 'until the round ends'
          };
        }
      }
      if (auction.current_stage < (auction.stages.length - 1)) {
        return {
          'countdown': ((new Date(auction.stages[auction.stages.length - 1].start) - current_time) / 1000),
          'start_time': false,
          'msg': 'until the results announcement'
        };
      }
    }

    function prepare_progress_timer_data(current_time, auction) {
        if (auction.current_stage === (auction.stages.length - 1)) {
          return {
            'countdown_seconds': false,
            'rounds_seconds': 0,
          };
        }
        if (auction.current_stage === -1) {
          return {
            'countdown_seconds': ((new Date(auction.stages[0].start) - current_time) / 1000),
            'rounds_seconds': ((new Date(auction.stages[0].start) - current_time) / 1000),
          };
        }
        return {
          'countdown_seconds': ((new Date(auction.stages[auction.current_stage + 1].start) - current_time) / 1000),
          'rounds_seconds': ((new Date(auction.stages[auction.current_stage + 1].start) - new Date(auction.stages[auction.current_stage].start)) / 1000),
        };

      }
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
    function format_date(date, lang, format) {
      return moment(date).locale(lang).format(format);
    }

    // Get round data
    function get_round_data(pause_index, auction_doc, Rounds) {
        if (pause_index == -1){
          return {
            'type': 'waiting'
          };
        }
        if (pause_index <= Rounds[0]) {
          return {
            'type': 'pause',
            'data': ['', '1', ]
          };
        }
        for (var i in Rounds) {
          if (pause_index < Rounds[i]) {
            return {
              'type': 'round',
              'data': parseInt(i)
            };
          } else if (pause_index == Rounds[i]) {
            return {
              'type': 'pause',
              'data': [(parseInt(i)).toString(), (parseInt(i) + 1).toString(), ]
            };
          }
        }

        if (pause_index < (auction_doc.stages.length - 1)) {
          return {
            'type': 'round',
            'data': Rounds.length
          };
        } else {
          return {
            'type': 'finish'
          };
        }
      }
      // Scroll functionality
    function scroll_to_stage(stage) {
      $timeout(function () {
        var stage_el = document.getElementById('stage-' + stage.toString());
        if (stage_el) {
          $log.debug('Scroll to:', stage_el);
          window.scrollBy(0, stage_el.getBoundingClientRect().top);
          if (document.getElementById('stage-' + stage.toString()).getBoundingClientRect().top == 0){
            window.scrollBy(0, -200);
          }
        }
      }, 1000);
    }
    return {
      'prepare_info_timer_data': prepare_info_timer_data,
      'prepare_progress_timer_data': prepare_progress_timer_data,
      'get_bidder_id': get_bidder_id,
      'format_date': format_date,
      'get_round_data': get_round_data,
      'scroll_to_stage': scroll_to_stage
    };
  }]);



angular.module('auction')
  .factory('aside', ['$modal', function ($modal) {

    var asideFactory = {
      open: function (config) {
        var options = angular.extend({}, config);
        // check placement is set correct
        // set aside classes
        options.windowClass = 'ng-aside horizontal left' + (options.windowClass ? ' ' + options.windowClass : '');
        delete options.placement
        return $modal.open(options);
      }
    };
    return angular.extend({}, $modal, asideFactory);
  }]);