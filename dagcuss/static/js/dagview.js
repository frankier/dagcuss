var Backbone = require('backbone');
var _ = require('underscore');
_.str = require('underscore.string');
_.mixin(_.extend(_.str.exports(), {
    includeString: _.str.include,
    reverseString: _.str.reverse,
    containsString: _.str.contains
}));
var converter = new Markdown.Converter();

_.templateSettings = {
  interpolate : /\{\{(.+?)\}\}/g
};

Jasinja.templates['post_content.html'].macros.url_for = function(ctx, tmpl, name, kwargs) {
    if (!_.has(url_for_data, name)) {
        return "nomatch";
    }
    var matchUrl;
    var matched = _.any(url_for_data[name], function(candidateTemplate) {
        try {
            matchUrl = _.template(candidateTemplate, kwargs || {});
        } catch (e) {
            if (e.name.toString() === "ReferenceError") {
                return false;
            } else {
                throw e;
            }
        }
        return true;
    });
    if (!matched) {
        return "nomatch";
    }
    return matchUrl;
}

Jasinja.filters.markdown = function(text) {
    //console.log('marking down', text);
    return converter.makeHtml(text);
}

var methodMap, getUrl;
methodMap = {
    'create': 'POST',
    'update': 'PUT',
    'delete': 'DELETE',
    'read' : 'GET'
};

getUrl = function(object) {
    if (!(object && object.url)) return null;
    return _.isFunction(object.url) ? object.url() : object.url;
};

Backbone.sync = function(method, model, options) {
    var params = {
        type: 'json',
        method: methodMap[method],
        headers: { 'Content-Type': 'application/json' },

        success: options.success,
        error: options.error,

        url: getUrl(model)
    };

    if (params.method !== 'GET' && params.method !== 'DELETE') {
        params.data = JSON.stringify(options.data || model.toJSON());
    }

    params = _.defaults(options, params)
    console.log(params);
    return $.ajax(params);
};

var Post = Backbone.Model.extend({
    element_type: "post",
    // parent replies
    // children replies
    // children post ids
    // parent post ids
    // children
    // parents

});

var TemplatePost = klass({
    initialize: function(post_model, posts, replies) {
        _.bindAll(this);
        this.model = post_model;
        this.posts = posts;
        this.replies = replies;
        this.title = post_model.get('title');
        this.body = post_model.get('body');
        this.at = $.moment(post_model.get('at')* 1000).format('YYYY-MM-DD HH:mm:ss');
        this.root = post_model.get('root');
        this.eid = post_model.id;
    },

    parents: function() {
        var self = this;
        return _.map(this.model.get('parents'), function(id) {
            return new TemplatePost(self.posts.get(self.replies.get(id).get('out_id')));
        });
    },

    children: function() {
        var self = this;
        return _.map(this.model.get('children'), function(id) {
            return new TemplatePost(self.posts.get(self.replies.get(id).get('in_id')));
        });
    },

    toString: function() {
        var result = "" + this.eid;
        if (this.title) {
            result += _.sprintf(" [%s]", this.title);
        }
        result += _.sprintf(" posted on %s", this.at);
        return result;
    }
});


var Reply = Backbone.Model.extend({
    element_type: "reply"
});

var Posts = Backbone.Collection.extend({
});

var Replies = Backbone.Collection.extend({
});

var Updater = klass({
    initialize: function(posts, replies) {
        this.posts = posts;
        this.replies = replies;
    },

    byTile: function(args) {
        Backbone.sync("read", null, {
            url: '/api/by-tile/',
            data: args.data,
            success: function(resp) {
                console.log(resp);
                _.each(resp.posts, function(post) {
                    this.posts.add(new Post(post));
                });
                _.each(resp.replies, function(reply) {
                    this.replies.add(new Reply(reply));
                });
                args.success(resp);
            },
            error: function(resp) {
                args.error(resp);
            }
        });
    },

    postDetail: function(args) {
        Backbone.sync("read", null, {
            url: _.sprintf('/api/post-detail/%d/', args.id),
            data: {
                extra_posts: args.extra_ids
            },
            success: function(resp) {
                console.log(resp);
                _.each(resp.posts, function(post_resp) {
                    if (post_resp.id === args.id) {
                        var post_model = this.posts.get(post_resp.id)
                        post_model.set('body', post_resp.body);
                    } else {
                        this.posts.add(new Post(post_resp));
                    }
                });
                args.success(resp);
            },
            error: function (resp) {
                args.error(resp);
            }
        });
    }
})

var PostView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this);
        this.posts = this.options.posts;
        this.replies = this.options.replies;
        this.updater = this.options.updater;
        this.model.view = this;
    },

    render: function() {
        this.circle = this.el.circle(this.model.get('x'), this.model.get('y'), 8)
            .attr("fill", "#f00")
            .hover(this.hoverIn, this.hoverOut)
            .click(this.click);
        if (this.model.id === this.posts.current) {
            this.startCurrent();
        }
    },

    hoverIn: function(evt) {
        if (this.model.id !== this.posts.current) {
            this.circle.attr("fill", "#a00");
        }
    },

    hoverOut: function(evt) {
        if (this.model.id !== this.posts.current) {
            this.circle.attr("fill", "#f00");
        }
    },

    click: function(evt) {
        var self = this;
        console.log('click');
        this.updater.postDetail({
            success: this.makeCurrent,
            id: this.model.id,
            extra_ids: _.difference(_.union(
                _.map(this.model.get('parents'), function(parent) {
                    return self.replies.get(parent).get('out_id')
                }),
                _.map(this.model.get('children'), function(child) {
                    return self.replies.get(child).get('in_id')
                })), this.posts.map(function(model) {
                    return model.id;
                }))
        });
    },

    makeCurrent: function() {
        var self = this;
        if (this.posts.current) {
            var oldCurrentView = this.posts.get(this.posts.current).view;
            oldCurrentView.endCurrent();
        }
        this.posts.current = this.model.id;
        this.startCurrent();
        var new_content = Jasinja.templates['post_content.html'].render({
            post: new TemplatePost(this.model, this.posts, this.replies)
        });
        $('#post').parent().html(new_content);
    },

    startCurrent: function() {
        this.circle.attr("fill", "#000");
    },

    endCurrent: function() {
        this.circle.attr("fill", "#f00");
    }
});

var ReplyView = Backbone.View.extend({
    render: function() {
        var reply = this.model;
        var pos = reply.get('pos');
        if (pos.length == 0) {
            return;
        }
        var startPos = _.first(pos);
        var curvesPos = _.rest(pos);
        var pathCommand = "M" + startPos[0] + ',' + startPos[1] + " C";
        pathCommand += _.chain(curvesPos)
            .groupBy(function(elem, i) {
                return Math.floor(i/3);
            })
            .values()
            .map(function(curveTo) {
                return _.chain(curveTo)
                    .map(function(coord) {
                        return coord.join(",");
                    }).value().join(" ");
            })
            .value().join(" C");
        //console.log(pathCommand);
        this.path = this.el.path(pathCommand);
    }
});

function pixelToTile(x) {
    return Math.floor((x + config.TILE_SIZE / 2) / config.TILE_SIZE);
}

var DAGView = Backbone.View.extend({
    el: $('#dagnav'),

    initialize: function(args) {
        _.bindAll(this);
        this.posts = this.options.posts;
        this.replies = this.options.replies;
        this.updater = this.options.updater;
        this.originX = 0;
        this.originY = -500;
        this.width = 500;
        this.height = 1000;
        this.cachedTiles = [];
        this.paper = new Raphael("dagnav", this.width, this.height);
        this.posts.current = static_post_id;
        console.log('this.posts.current', this.posts.current);
        this.update(); // TODO: "Bootstrap" instead
        $(this.paper.canvas).mousedown(this.dragStart).mouseup(this.dragEnd);
    },

    dragStart: function(evt) {
        this.beforeDragX = evt.clientX;
        this.beforeDragY = evt.clientY;
    },

    dragEnd: function(evt) {
        var diffX = evt.clientX - this.beforeDragX
        var diffY = evt.clientY - this.beforeDragY
        this.originX -= diffX;
        this.originY -= diffY;
        this.update();
    },

    update: function() {
        var self = this;
        this.paper.setViewBox(self.originX, self.originY, self.width, self.height);
        var xMinTile = pixelToTile(self.originX);
        var xMaxTile = pixelToTile(self.originX + self.width);
        var yMinTile = pixelToTile(self.originY);
        var yMaxTile = pixelToTile(self.originY + self.height);
        var xTileRange = _.range(xMinTile, xMaxTile + 1);
        var yTileRange = _.range(yMinTile, yMaxTile + 1)
        var candidateTiles = _.flatten(_.map(xTileRange, function(x) {return _.map(yTileRange, function(y) {return [x, y]})}), true);
        var newTiles = _.reject(candidateTiles, function (candidateTile) {
            return _.any(_.map(self.cachedTiles, function (cachedTile) {
                return _.isEqual(candidateTile, cachedTile);
            }));
        });
        //console.log('newTiles', newTiles);
        if (_.size(newTiles) === 0) {
            return;
        }
        this.updater.byTile({
            data: {
                tile_x: _.map(newTiles, function(tile) {
                    return tile[0];
                }),
                tile_y: _.map(newTiles, function(tile) {
                    return tile[1];
                })
            },
            success: function(collection, resp) {
                self.cachedTiles.push.apply(self.cachedTiles, newTiles);
                self.render();
            }
        });
    },

    render: function() {
        var self = this;
        this.posts.each(function(model) {
            if (!model.drawn) {
                var view = new PostView({
                    el: self.paper,
                    model: model,
                    posts: this.posts,
                    replies: this.replies,
                    updater: this.updater
                });
                view.render();
                model.drawn = true;
            }
        });
        this.replies.each(function(model) {
            if (!model.drawn) {
                var view = new ReplyView({
                    el: self.paper,
                    model: model
                });
                view.render();
                model.drawn = true;
            }
        });
    }
});

$.domReady(function() {
    console.log("domReady");
    posts = new Posts();
    replies = new Replies();
    updater = new Updater(posts, replies);
    dagView = new DAGView({
        posts: posts,
        replies: replies,
        updater: updater
    });
});
